from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict
from datetime import date

from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.db import connections
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework import permissions
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import UserOrAccessAgentKeyPermission
from api.serializers import (
    AccessEventSerializer,
    ClientSerializer,
    DonationSerializer,
    ExpenseCategorizationRuleSerializer,
    ExpenseCategorizeSerializer,
    ExpenseImportSerializer,
    InvoiceScheduleSerializer,
    ImportedBankTransactionSerializer,
    InvoiceSerializer,
    ManualPaymentSerializer,
    ManualPaymentEntrySerializer,
    MemberBalanceSerializer,
    MemberSerializer,
    PaymentAllocationSerializer,
    PaymentSerializer,
    ReportQuerySerializer,
    StripeCheckoutRequestSerializer,
    StripeSetupIntentRequestSerializer,
)
from apps.access.models import AccessAllowlistSnapshot
from apps.access.services import build_allowlist_snapshot, record_access_event
from apps.audit.models import AuditLog
from apps.billing.models import Invoice, InvoiceSchedule, Payment, ProcessorChoices, WebhookEvent
from apps.billing.services import (
    allocate_payment_fifo,
    build_ar_aging_report,
    create_checkout_session,
    create_setup_intent,
    issue_invoice,
    ingest_stripe_event,
    record_manual_payment,
    construct_stripe_event,
    void_invoice,
)
from apps.common.utils import json_ready
from apps.donations.models import Donation
from apps.donations.services import process_everyorg_webhook
from apps.expenses.models import (
    Expense,
    ExpenseCategorizationRule,
    ExpenseCategory,
    ExpenseImportBatch,
    ImportedBankTransaction,
)
from apps.expenses.services import categorize_imported_transaction, import_expense_csv
from apps.ledger.services import render_financial_report
from apps.members.models import Client, Member
from apps.members.services import get_member_balance


class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all().order_by("id")
    serializer_class = ClientSerializer


class HealthCheckView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            return Response({"status": "error"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"status": "ok"})


class MemberViewSet(viewsets.ModelViewSet):
    queryset = Member.objects.select_related("client").all()
    serializer_class = MemberSerializer

    @action(detail=True, methods=["get"], url_path="balance")
    def balance(self, request, pk=None):  # type: ignore[override]
        member = self.get_object()
        balance = get_member_balance(member)
        return Response(MemberBalanceSerializer.from_balance(balance))

    @action(detail=True, methods=["get"], url_path="history")
    def history(self, request, pk=None):  # type: ignore[override]
        member = self.get_object()
        membership_terms = [
            {
                "id": term.id,
                "effective_from": term.effective_from,
                "effective_to": term.effective_to,
                "membership_class": term.membership_class,
                "monthly_dues_cents": term.monthly_dues_cents,
                "voting_eligible": term.voting_eligible,
                "door_access_enabled": term.door_access_enabled,
                "reason": term.reason,
            }
            for term in member.membership_terms.order_by("effective_from", "id")
        ]
        audit_log = [
            {
                "id": entry.id,
                "occurred_at": entry.occurred_at,
                "action": entry.action,
                "before_json": entry.before_json,
                "after_json": entry.after_json,
                "reason": entry.reason,
            }
            for entry in AuditLog.objects.filter(entity_type="Member", entity_id=str(member.pk)).order_by("occurred_at", "id")
        ]
        return Response({"membership_terms": membership_terms, "audit_log": audit_log})

    @action(detail=True, methods=["post"], url_path="manual-payment")
    def manual_payment(self, request, pk=None):  # type: ignore[override]
        member = self.get_object()
        serializer = ManualPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = record_manual_payment(
            member=member,
            amount_cents=serializer.validated_data["amount_cents"],
            payment_method=serializer.validated_data["payment_method"],
            source_type=serializer.validated_data["source_type"],
            note=serializer.validated_data.get("note", ""),
        )
        return Response(
            {
                "payment_id": payment.pk,
                "status": payment.status,
                "allocated_cents": sum(allocation.allocated_cents for allocation in payment.allocations.all()),
            },
            status=status.HTTP_201_CREATED,
        )


class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.prefetch_related("lines").all().order_by("due_date", "issue_date", "id")
    serializer_class = InvoiceSerializer

    @action(detail=True, methods=["post"], url_path="issue")
    def issue(self, request, pk=None):  # type: ignore[override]
        invoice = issue_invoice(self.get_object())
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=["post"], url_path="void")
    def void(self, request, pk=None):  # type: ignore[override]
        invoice = void_invoice(self.get_object())
        return Response(InvoiceSerializer(invoice).data)


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Payment.objects.all().order_by("-received_at", "-id")
    serializer_class = PaymentSerializer

    @action(detail=True, methods=["post"], url_path="allocate")
    def allocate(self, request, pk=None):  # type: ignore[override]
        payment = self.get_object()
        serializer = PaymentAllocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoices = None
        if serializer.validated_data.get("invoice_ids"):
            invoices = list(Invoice.objects.filter(pk__in=serializer.validated_data["invoice_ids"]).order_by("due_date", "id"))
        try:
            result = allocate_payment_fifo(payment, invoices=invoices)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"allocated_cents": result.allocated_cents, "invoice_numbers": result.invoice_numbers})


class InvoiceScheduleViewSet(viewsets.ModelViewSet):
    queryset = InvoiceSchedule.objects.select_related("client", "member").all().order_by("id")
    serializer_class = InvoiceScheduleSerializer


class DonationViewSet(viewsets.ModelViewSet):
    queryset = Donation.objects.all().order_by("-donation_date", "-id")
    serializer_class = DonationSerializer
    http_method_names = ["get", "post"]


class ExpenseCategorizationRuleViewSet(viewsets.ModelViewSet):
    queryset = ExpenseCategorizationRule.objects.select_related("expense_category").all().order_by("priority", "id")
    serializer_class = ExpenseCategorizationRuleSerializer


class StripeCheckoutSessionView(APIView):
    def post(self, request):
        serializer = StripeCheckoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = Member.objects.select_related("client").get(pk=serializer.validated_data["member_id"])
        session = create_checkout_session(
            member=member,
            mode=serializer.validated_data["mode"],
            amount_cents=serializer.validated_data.get("amount_cents"),
            success_url=serializer.validated_data.get("success_url"),
            cancel_url=serializer.validated_data.get("cancel_url"),
        )
        return Response({"id": session.get("id"), "url": session.get("url"), "payload": session})


class StripeSetupIntentView(APIView):
    def post(self, request):
        serializer = StripeSetupIntentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = Member.objects.select_related("client").get(pk=serializer.validated_data["member_id"])
        setup_intent = create_setup_intent(member)
        return Response(
            {
                "id": setup_intent.get("id"),
                "client_secret": setup_intent.get("client_secret"),
                "payload": setup_intent,
            }
        )


@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookView(View):
    def post(self, request):
        payload = request.body
        signature = request.META.get("HTTP_STRIPE_SIGNATURE", "")
        fallback_event_id = f"invalid-{hashlib.sha256(payload).hexdigest()}"
        try:
            event = construct_stripe_event(payload, signature)
        except Exception:
            WebhookEvent.objects.update_or_create(
                processor=ProcessorChoices.STRIPE,
                event_id=fallback_event_id,
                defaults={
                    "payload_json": json.loads(payload.decode("utf-8") or "{}") if payload else {},
                    "signature_valid": False,
                },
            )
            return HttpResponseBadRequest("Invalid Stripe signature.")

        ingest_stripe_event(event._to_dict_recursive())
        return JsonResponse({"status": "ok"})


@method_decorator(csrf_exempt, name="dispatch")
class EveryOrgWebhookView(View):
    def post(self, request):
        configured_token = getattr(settings, "EVERYORG_WEBHOOK_TOKEN", "")
        request_token = request.GET.get("token") or request.headers.get("X-Everyorg-Webhook-Token", "")
        if configured_token and request_token != configured_token:
            return JsonResponse({"detail": "Invalid Every.org webhook token."}, status=403)
        payload = json.loads(request.body.decode("utf-8") or "{}")
        donation = process_everyorg_webhook(payload)
        return JsonResponse({"status": "ok", "donation_id": donation.pk})


class AllowlistView(APIView):
    permission_classes = [UserOrAccessAgentKeyPermission]

    def get(self, request):
        etag = request.query_params.get("v")
        latest = AccessAllowlistSnapshot.objects.order_by("-generated_at", "-id").first()
        if latest and etag and etag == latest.etag:
            return Response(status=status.HTTP_304_NOT_MODIFIED)
        snapshot = latest or build_allowlist_snapshot()
        return Response(
            {
                "etag": snapshot.etag,
                "generated_at": snapshot.generated_at,
                "signature": snapshot.signature,
                "payload": snapshot.payload_json,
            }
        )


class MemberEntitlementView(APIView):
    permission_classes = [UserOrAccessAgentKeyPermission]

    def get(self, request, member_id: int):
        member = Member.objects.select_related("client").get(pk=member_id)
        return Response(
            {
                "member_id": member.pk,
                "member_number": member.member_number,
                "door_access_enabled": member.door_access_enabled,
                "updated_at": member.updated_at,
            }
        )


class AccessEventView(APIView):
    permission_classes = [UserOrAccessAgentKeyPermission]

    def post(self, request):
        serializer = AccessEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = None
        member_id = serializer.validated_data.get("member_id")
        if member_id:
            member = Member.objects.filter(pk=member_id).first()
        event = record_access_event(
            credential_uid=serializer.validated_data["credential_uid"],
            result=serializer.validated_data["result"],
            member=member,
            details=serializer.validated_data.get("details") or {},
        )
        return Response({"id": event.pk}, status=status.HTTP_201_CREATED)


class FinancialReportView(APIView):
    def get(self, request):
        serializer = ReportQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        report = render_financial_report(
            start=serializer.validated_data["from"],
            end=serializer.validated_data["to"],
        )
        return Response(json_ready(asdict(report)))


class FinancialReportCsvView(APIView):
    def get(self, request):
        serializer = ReportQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        report = render_financial_report(
            start=serializer.validated_data["from"],
            end=serializer.validated_data["to"],
        )
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="financial-report.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "from",
                "to",
                "earned_dues_cents",
                "cash_receipts_cents",
                "donations_cents",
                "expenses_cents",
                "outstanding_receivables_cents",
                "member_credit_cents",
            ]
        )
        writer.writerow(
            [
                report.start.isoformat(),
                report.end.isoformat(),
                report.earned_dues_cents,
                report.cash_receipts_cents,
                report.donations_cents,
                report.expenses_cents,
                report.outstanding_receivables_cents,
                report.member_credit_cents,
            ]
        )
        return response


class MemberBalancesReportView(APIView):
    def get(self, request):
        payload = []
        for member in Member.objects.select_related("client").order_by("pk"):
            balance = get_member_balance(member)
            payload.append(
                {
                    "member_id": member.pk,
                    "member_name": member.client.display_name,
                    "membership_status": member.status,
                    "credit_cents": balance.credit_cents,
                    "receivable_cents": balance.receivable_cents,
                    "arrears_months": balance.arrears_months,
                    "next_due_date": balance.next_due_date,
                }
            )
        return Response(payload)


class ARAgingReportView(APIView):
    def get(self, request):
        return Response(build_ar_aging_report(as_of=date.today()))


class ManualPaymentEntryView(APIView):
    def post(self, request):
        serializer = ManualPaymentEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = record_manual_payment(
            client=serializer.validated_data.get("client"),
            member=serializer.validated_data.get("member"),
            received_at=serializer.validated_data.get("received_at"),
            amount_cents=serializer.validated_data["amount_cents"],
            currency=serializer.validated_data.get("currency"),
            payment_method=serializer.validated_data.get("payment_method", Payment.PaymentMethod.OTHER),
            source_type=serializer.validated_data["source_type"],
            status=serializer.validated_data.get("status", Payment.Status.SUCCEEDED),
            note=serializer.validated_data.get("notes", ""),
            metadata=serializer.validated_data.get("metadata"),
        )
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class ExpenseImportCsvView(APIView):
    def post(self, request):
        serializer = ExpenseImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        batch, transactions = import_expense_csv(
            source_name=serializer.validated_data["source_name"],
            parser_key=serializer.validated_data["parser_key"],
            csv_content=serializer.validated_data["csv_content"],
        )
        return Response(
            {
                "batch_id": batch.pk,
                "transactions": ImportedBankTransactionSerializer(transactions, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


class ExpenseImportBatchListView(APIView):
    def get(self, request):
        payload = [
            {
                "id": batch.pk,
                "source_name": batch.source.name,
                "imported_at": batch.imported_at,
                "transaction_count": batch.transactions.count(),
            }
            for batch in ExpenseImportBatch.objects.select_related("source").order_by("-imported_at", "-id")
        ]
        return Response(payload)


class ExpenseCategorizeView(APIView):
    def post(self, request, transaction_id: int):
        serializer = ExpenseCategorizeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        transaction = ImportedBankTransaction.objects.get(pk=transaction_id)
        category, _ = ExpenseCategory.objects.get_or_create(
            code=serializer.validated_data["category_code"],
            defaults={"name": serializer.validated_data["category_name"]},
        )
        expense = categorize_imported_transaction(transaction, category, reconciled=True)
        return Response({"transaction_id": transaction.pk, "expense_id": expense.pk, "category": category.code})


class MemberBalancesCsvView(APIView):
    def get(self, request):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="member-balances.csv"'
        writer = csv.writer(response)
        writer.writerow(["member_id", "member_name", "status", "credit_cents", "receivable_cents", "arrears_months", "next_due_date"])
        for member in Member.objects.select_related("client").order_by("pk"):
            balance = get_member_balance(member)
            writer.writerow(
                [
                    member.pk,
                    member.client.display_name,
                    member.status,
                    balance.credit_cents,
                    balance.receivable_cents,
                    balance.arrears_months,
                    balance.next_due_date.isoformat() if balance.next_due_date else "",
                ]
            )
        return response
