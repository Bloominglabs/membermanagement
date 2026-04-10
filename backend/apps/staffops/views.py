from __future__ import annotations

from datetime import date

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.access.models import AccessAllowlistSnapshot, AccessEvent, RFIDCredential
from apps.access.services import build_allowlist_snapshot
from apps.audit.models import AuditLog
from apps.audit.services import log_audit_event
from apps.billing.models import Invoice, InvoiceSchedule, Payment, ProcessorChoices, WebhookEvent
from apps.billing.services import (
    allocate_payment_fifo,
    build_ar_aging_report,
    create_one_off_invoice,
    generate_due_scheduled_invoices,
    issue_invoice,
    monthly_dues_close,
    reconcile_unposted_stripe_payments,
    record_manual_payment,
    void_invoice,
    dues_autopay_run,
)
from apps.donations.models import Donation
from apps.expenses.models import ExpenseCategory, ExpenseImportBatch, ImportedBankTransaction
from apps.expenses.services import categorize_imported_transaction, import_expense_csv
from apps.ledger.services import render_financial_report
from apps.members.models import Member
from apps.members.services import get_member_balance, member_snapshot, sync_membership_term, update_member_status_from_balance
from apps.staffops.forms import (
    AuditFilterForm,
    BillingRunForm,
    DoorAccessForm,
    ExpenseCategorizeForm,
    ExpenseImportForm,
    ManualPaymentForm,
    OneOffInvoiceForm,
    RFIDCredentialForm,
)


def _admin_change_url(app_label: str, model_name: str, object_id: int) -> str:
    return reverse(f"admin:{app_label}_{model_name}_change", args=[object_id])


def _parse_report_dates(request) -> tuple[date, date]:
    today = timezone.localdate()
    default_start = today.replace(day=1)
    start = request.GET.get("from") or default_start.isoformat()
    end = request.GET.get("to") or today.isoformat()
    return date.fromisoformat(start), date.fromisoformat(end)


def _run_enforcement() -> int:
    updated = 0
    for member in Member.objects.select_related("client").all():
        previous = member.status
        update_member_status_from_balance(member)
        member.refresh_from_db(fields=["status"])
        if member.status != previous:
            updated += 1
    return updated


@staff_member_required
@require_GET
def home(request):
    latest_snapshot = AccessAllowlistSnapshot.objects.first()
    context = {
        "active_nav": "home",
        "active_members_count": Member.objects.filter(status=Member.Status.ACTIVE).count(),
        "past_due_members_count": Member.objects.filter(status=Member.Status.PAST_DUE).count(),
        "suspended_members_count": Member.objects.filter(status=Member.Status.SUSPENDED).count(),
        "autopay_members_count": Member.objects.filter(autopay_enabled=True).count(),
        "overdue_invoices_count": Invoice.objects.exclude(status__in=[Invoice.Status.VOID, Invoice.Status.PAID]).filter(
            due_date__lt=timezone.localdate()
        ).count(),
        "unreconciled_expenses_count": ImportedBankTransaction.objects.filter(is_reconciled=False).count(),
        "invalid_webhooks_count": WebhookEvent.objects.filter(signature_valid=False).count(),
        "pending_stripe_reconciliation_count": reconcile_unposted_stripe_payments(),
        "latest_allowlist_snapshot": latest_snapshot,
        "latest_access_event": AccessEvent.objects.select_related("member", "member__client").first(),
    }
    return render(request, "staffops/home.html", context)


@staff_member_required
@require_GET
def member_list(request):
    members = Member.objects.select_related("client").all()
    query = request.GET.get("query", "").strip()
    status = request.GET.get("status", "").strip()
    membership_class = request.GET.get("membership_class", "").strip()
    autopay_enabled = request.GET.get("autopay_enabled", "").strip()
    door_access_enabled = request.GET.get("door_access_enabled", "").strip()

    if query:
        members = members.filter(
            Q(member_number__icontains=query)
            | Q(client__display_name_text__icontains=query)
            | Q(client__first_name__icontains=query)
            | Q(client__last_name__icontains=query)
            | Q(client__email__icontains=query)
        )
    if status:
        members = members.filter(status=status)
    if membership_class:
        members = members.filter(membership_class=membership_class)
    if autopay_enabled in {"0", "1"}:
        members = members.filter(autopay_enabled=autopay_enabled == "1")
    if door_access_enabled in {"0", "1"}:
        members = members.filter(door_access_enabled=door_access_enabled == "1")

    member_rows = [{"member": member, "balance": get_member_balance(member)} for member in members.order_by("client__last_name", "client__first_name", "id")]
    context = {
        "active_nav": "members",
        "member_rows": member_rows,
        "query": query,
        "status_filter": status,
        "membership_class_filter": membership_class,
        "autopay_enabled_filter": autopay_enabled,
        "door_access_enabled_filter": door_access_enabled,
    }
    return render(request, "staffops/member_list.html", context)


@staff_member_required
@require_GET
def member_workspace(request, member_id: int):
    member = get_object_or_404(Member.objects.select_related("client"), pk=member_id)
    context = {
        "active_nav": "members",
        "member": member,
        "balance": get_member_balance(member),
        "current_term": member.membership_terms.order_by("-effective_from", "-id").first(),
        "credentials": member.rfid_credentials.order_by("uid"),
        "recent_invoices": member.invoices.order_by("-due_date", "-issue_date", "-id")[:10],
        "recent_payments": member.payments.order_by("-received_at", "-id")[:10],
        "recent_audit_entries": AuditLog.objects.filter(entity_type="Member", entity_id=str(member.pk)).order_by("-occurred_at", "-id")[:20],
        "invoice_schedules": member.invoice_schedules.order_by("id"),
        "manual_payment_form": ManualPaymentForm(initial={"source_type": Payment.SourceType.DUES_PAYMENT}),
        "one_off_invoice_form": OneOffInvoiceForm(),
        "rfid_form": RFIDCredentialForm(),
        "door_access_form": DoorAccessForm(initial={"door_access_enabled": member.door_access_enabled}),
        "member_admin_url": _admin_change_url("members", "member", member.pk),
        "client_admin_url": _admin_change_url("members", "client", member.client.pk),
    }
    return render(request, "staffops/member_workspace.html", context)


@staff_member_required
@require_POST
def member_manual_payment(request, member_id: int):
    member = get_object_or_404(Member.objects.select_related("client"), pk=member_id)
    form = ManualPaymentForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Manual payment details were invalid.")
        return redirect("staffops:member-workspace", member_id=member.pk)

    payment = record_manual_payment(
        member=member,
        amount_cents=form.cleaned_data["amount_cents"],
        source_type=form.cleaned_data["source_type"],
        note=form.cleaned_data["note"],
    )
    log_audit_event(
        actor=request.user.get_username(),
        actor_type="user",
        entity_type="Payment",
        entity_id=str(payment.pk),
        action="payment.created",
        after_json={"amount_cents": payment.amount_cents, "member_id": member.pk},
        message=f"Manual payment {payment.pk} created from staff UI",
    )
    messages.success(request, f"Recorded manual payment of {payment.amount_cents} cents.")
    return redirect("staffops:member-workspace", member_id=member.pk)


@staff_member_required
@require_POST
def member_one_off_invoice(request, member_id: int):
    member = get_object_or_404(Member.objects.select_related("client"), pk=member_id)
    form = OneOffInvoiceForm(request.POST)
    if not form.is_valid():
        messages.error(request, "One-off invoice details were invalid.")
        return redirect("staffops:member-workspace", member_id=member.pk)

    invoice = create_one_off_invoice(
        member=member,
        invoice_number=form.cleaned_data["invoice_number"],
        description=form.cleaned_data["description"],
        amount_cents=form.cleaned_data["amount_cents"],
    )
    log_audit_event(
        actor=request.user.get_username(),
        actor_type="user",
        entity_type="Invoice",
        entity_id=str(invoice.pk),
        action="invoice.created",
        after_json={"invoice_number": invoice.invoice_number, "member_id": member.pk},
        message=f"Invoice {invoice.invoice_number} created from staff UI",
    )
    messages.success(request, f"Created invoice {invoice.invoice_number}.")
    return redirect("staffops:member-workspace", member_id=member.pk)


@staff_member_required
@require_POST
def member_add_rfid(request, member_id: int):
    member = get_object_or_404(Member.objects.select_related("client"), pk=member_id)
    form = RFIDCredentialForm(request.POST)
    if not form.is_valid():
        messages.error(request, "RFID credential details were invalid.")
        return redirect("staffops:member-workspace", member_id=member.pk)

    credential = RFIDCredential.objects.create(
        member=member,
        uid=form.cleaned_data["uid"],
        label=form.cleaned_data["label"],
    )
    log_audit_event(
        actor=request.user.get_username(),
        actor_type="user",
        entity_type="RFIDCredential",
        entity_id=str(credential.pk),
        action="rfid.created",
        after_json={"uid": credential.uid, "member_id": member.pk},
        message=f"RFID credential {credential.uid} added from staff UI",
    )
    messages.success(request, f"Added credential {credential.uid}.")
    return redirect("staffops:member-workspace", member_id=member.pk)


@staff_member_required
@require_POST
def member_deactivate_rfid(request, member_id: int, credential_id: int):
    member = get_object_or_404(Member, pk=member_id)
    credential = get_object_or_404(RFIDCredential, pk=credential_id, member=member)
    credential.is_active = False
    credential.save(update_fields=["is_active"])
    log_audit_event(
        actor=request.user.get_username(),
        actor_type="user",
        entity_type="RFIDCredential",
        entity_id=str(credential.pk),
        action="rfid.deactivated",
        before_json={"is_active": True},
        after_json={"is_active": False},
        message=f"RFID credential {credential.uid} deactivated from staff UI",
    )
    messages.success(request, f"Deactivated credential {credential.uid}.")
    return redirect("staffops:member-workspace", member_id=member.pk)


@staff_member_required
@require_POST
def member_update_door_access(request, member_id: int):
    member = get_object_or_404(Member.objects.select_related("client"), pk=member_id)
    form = DoorAccessForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Door access settings were invalid.")
        return redirect("staffops:member-workspace", member_id=member.pk)

    before = member_snapshot(member)
    member.door_access_enabled = form.cleaned_data["door_access_enabled"]
    member.save(update_fields=["door_access_enabled", "updated_at"])
    sync_membership_term(member, reason="Door access updated from staff UI")
    log_audit_event(
        actor=request.user.get_username(),
        actor_type="user",
        entity_type="Member",
        entity_id=str(member.pk),
        action="member.door_access.updated",
        before_json={"door_access_enabled": before["door_access_enabled"]},
        after_json={"door_access_enabled": member.door_access_enabled},
        message=f"Door access updated for member {member.pk}",
    )
    messages.success(request, f"Door access {'enabled' if member.door_access_enabled else 'disabled'} for {member.client.display_name}.")
    return redirect("staffops:member-workspace", member_id=member.pk)


@staff_member_required
@require_GET
def billing_dashboard(request):
    context = {
        "active_nav": "billing",
        "autopay_members_count": Member.objects.filter(autopay_enabled=True).count(),
        "pending_stripe_reconciliation_count": reconcile_unposted_stripe_payments(),
        "overdue_invoices_count": Invoice.objects.exclude(status__in=[Invoice.Status.VOID, Invoice.Status.PAID]).filter(
            due_date__lt=timezone.localdate()
        ).count(),
        "active_schedule_count": InvoiceSchedule.objects.filter(active=True).count(),
        "recent_invoices": Invoice.objects.select_related("member", "client").order_by("-created_at", "-id")[:10],
        "recent_payments": Payment.objects.select_related("member", "client").order_by("-received_at", "-id")[:10],
        "invoice_schedules": InvoiceSchedule.objects.select_related("member", "client").order_by("id")[:20],
        "run_form": BillingRunForm(),
    }
    return render(request, "staffops/billing_dashboard.html", context)


@staff_member_required
@require_POST
def billing_run(request):
    form = BillingRunForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Billing action was invalid.")
        return redirect("staffops:billing-dashboard")

    action = form.cleaned_data["action"]
    if action == BillingRunForm.ACTION_MONTHLY_DUES_CLOSE:
        invoices = monthly_dues_close()
        messages.success(request, f"Monthly dues close confirmed {len(invoices)} invoices.")
    elif action == BillingRunForm.ACTION_SCHEDULED_INVOICES:
        invoices = generate_due_scheduled_invoices()
        messages.success(request, f"Generated {len(invoices)} scheduled invoices.")
    elif action == BillingRunForm.ACTION_AUTOPAY:
        results = dues_autopay_run()
        messages.success(request, f"Created {len(results)} autopay Stripe PaymentIntents.")
    elif action == BillingRunForm.ACTION_ENFORCEMENT:
        updated = _run_enforcement()
        messages.success(request, f"Updated {updated} member statuses.")
    else:
        pending = reconcile_unposted_stripe_payments()
        messages.info(request, f"{pending} Stripe payments still need reconciliation.")
    return redirect("staffops:billing-dashboard")


@staff_member_required
@require_GET
def invoice_review(request):
    invoices = Invoice.objects.select_related("member", "client").all()
    status = request.GET.get("status", "").strip()
    invoice_type = request.GET.get("invoice_type", "").strip()
    query = request.GET.get("query", "").strip()
    if status:
        invoices = invoices.filter(status=status)
    if invoice_type:
        invoices = invoices.filter(invoice_type=invoice_type)
    if query:
        invoices = invoices.filter(
            Q(invoice_number__icontains=query)
            | Q(client__display_name_text__icontains=query)
            | Q(client__email__icontains=query)
        )
    context = {
        "active_nav": "billing",
        "invoices": invoices.order_by("-due_date", "-issue_date", "-id")[:100],
        "status_filter": status,
        "invoice_type_filter": invoice_type,
        "query": query,
    }
    return render(request, "staffops/invoice_review.html", context)


@staff_member_required
@require_POST
def invoice_issue_action(request, invoice_id: int):
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    issue_invoice(invoice)
    messages.success(request, f"Issued invoice {invoice.invoice_number}.")
    return redirect("staffops:invoice-review")


@staff_member_required
@require_POST
def invoice_void_action(request, invoice_id: int):
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    void_invoice(invoice)
    messages.success(request, f"Voided invoice {invoice.invoice_number}.")
    return redirect("staffops:invoice-review")


@staff_member_required
@require_GET
def payment_review(request):
    payments = Payment.objects.select_related("member", "client").all()
    status = request.GET.get("status", "").strip()
    source_type = request.GET.get("source_type", "").strip()
    processor = request.GET.get("processor", "").strip()
    unreconciled = request.GET.get("unreconciled", "").strip()
    if status:
        payments = payments.filter(status=status)
    if source_type:
        payments = payments.filter(source_type=source_type)
    if processor:
        payments = payments.filter(processor=processor)
    if unreconciled == "1":
        payments = payments.filter(processor=ProcessorChoices.STRIPE, processor_balance_txn_id__isnull=True)

    payment_rows = []
    for payment in payments.order_by("-received_at", "-id")[:100]:
        available_invoices = []
        if payment.member_id:
            available_invoices = list(
                Invoice.objects.filter(member=payment.member)
                .exclude(status=Invoice.Status.VOID)
                .exclude(status=Invoice.Status.PAID)
                .order_by("due_date", "issue_date", "id")
            )
        payment_rows.append({"payment": payment, "available_invoices": available_invoices})

    context = {
        "active_nav": "billing",
        "payment_rows": payment_rows,
        "status_filter": status,
        "source_type_filter": source_type,
        "processor_filter": processor,
        "unreconciled_filter": unreconciled,
    }
    return render(request, "staffops/payment_review.html", context)


@staff_member_required
@require_POST
def payment_allocate_action(request, payment_id: int):
    payment = get_object_or_404(Payment.objects.select_related("member"), pk=payment_id)
    invoice_ids = [int(invoice_id) for invoice_id in request.POST.getlist("invoice_ids") if invoice_id]
    invoices = list(Invoice.objects.filter(pk__in=invoice_ids).order_by("due_date", "id")) if invoice_ids else None
    result = allocate_payment_fifo(payment, invoices=invoices)
    messages.success(request, f"Allocated {result.allocated_cents} cents across {len(result.invoice_numbers)} invoices.")
    return redirect("staffops:payment-review")


@staff_member_required
@require_GET
def donation_list(request):
    donations = Donation.objects.order_by("-donation_date", "-id")[:100]
    return render(
        request,
        "staffops/donation_list.html",
        {"active_nav": "donations", "donations": donations},
    )


@staff_member_required
@require_GET
def expense_dashboard(request):
    context = {
        "active_nav": "expenses",
        "import_form": ExpenseImportForm(initial={"parser_key": "generic_csv"}),
        "recent_batches": ExpenseImportBatch.objects.select_related("source").order_by("-imported_at", "-id")[:20],
        "uncategorized_transactions": ImportedBankTransaction.objects.select_related("expense").filter(expense__isnull=True).order_by(
            "-posted_on", "-id"
        )[:50],
        "categorized_transactions": ImportedBankTransaction.objects.select_related("expense", "expense__category").filter(
            expense__isnull=False
        ).order_by("-posted_on", "-id")[:50],
        "categorize_form": ExpenseCategorizeForm(),
    }
    return render(request, "staffops/expense_dashboard.html", context)


@staff_member_required
@require_POST
def expense_import_action(request):
    form = ExpenseImportForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Expense import payload was invalid.")
        return redirect("staffops:expense-dashboard")

    batch, transactions = import_expense_csv(
        source_name=form.cleaned_data["source_name"],
        parser_key=form.cleaned_data["parser_key"],
        csv_content=form.cleaned_data["csv_content"],
    )
    messages.success(request, f"Imported {len(transactions)} transactions in batch {batch.pk}.")
    return redirect("staffops:expense-dashboard")


@staff_member_required
@require_POST
def expense_categorize_action(request, transaction_id: int):
    transaction = get_object_or_404(ImportedBankTransaction, pk=transaction_id)
    form = ExpenseCategorizeForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Expense categorization details were invalid.")
        return redirect("staffops:expense-dashboard")

    category, _ = ExpenseCategory.objects.get_or_create(
        code=form.cleaned_data["category_code"],
        defaults={"name": form.cleaned_data["category_name"]},
    )
    if category.name != form.cleaned_data["category_name"]:
        category.name = form.cleaned_data["category_name"]
        category.save(update_fields=["name"])

    categorize_imported_transaction(transaction, category, reconciled=form.cleaned_data["reconciled"])
    messages.success(request, f"Categorized transaction {transaction.pk} as {category.code}.")
    return redirect("staffops:expense-dashboard")


@staff_member_required
@require_GET
def access_dashboard(request):
    context = {
        "active_nav": "access",
        "latest_snapshot": AccessAllowlistSnapshot.objects.first(),
        "credentials": RFIDCredential.objects.select_related("member", "member__client").order_by("uid")[:100],
        "access_events": AccessEvent.objects.select_related("member", "member__client").order_by("-occurred_at", "-id")[:100],
    }
    return render(request, "staffops/access_dashboard.html", context)


@staff_member_required
@require_POST
def refresh_allowlist_action(request):
    snapshot = build_allowlist_snapshot()
    messages.success(request, f"Created allowlist snapshot {snapshot.etag}.")
    return redirect("staffops:access-dashboard")


@staff_member_required
@require_GET
def reports_dashboard(request):
    start, end = _parse_report_dates(request)
    report = render_financial_report(start=start, end=end)
    ar_aging = build_ar_aging_report(as_of=end)
    balances = [
        {"member": member, "balance": get_member_balance(member)}
        for member in Member.objects.select_related("client").order_by("client__last_name", "client__first_name", "id")
    ]
    context = {
        "active_nav": "reports",
        "start": start,
        "end": end,
        "financial_report": report,
        "member_balances": balances,
        "ar_aging": ar_aging,
        "ar_aging_rows": [
            ("Total Receivables", ar_aging["total_receivables_cents"]),
            ("Current", ar_aging["buckets"]["current"]),
            ("1_30", ar_aging["buckets"]["1_30"]),
            ("31_60", ar_aging["buckets"]["31_60"]),
            ("61_90", ar_aging["buckets"]["61_90"]),
            ("Over 90", ar_aging["buckets"]["over_90"]),
        ],
        "financial_export_url": f"/api/exports/financial.csv?from={start.isoformat()}&to={end.isoformat()}",
        "member_balances_export_url": "/api/exports/member-balances.csv",
    }
    return render(request, "staffops/reports_dashboard.html", context)


@staff_member_required
@require_GET
def audit_timeline(request):
    form = AuditFilterForm(request.GET)
    logs = AuditLog.objects.all()
    if form.is_valid():
        if form.cleaned_data["entity_type"]:
            logs = logs.filter(entity_type=form.cleaned_data["entity_type"])
        if form.cleaned_data["action"]:
            logs = logs.filter(action=form.cleaned_data["action"])
        if form.cleaned_data["actor"]:
            logs = logs.filter(actor__icontains=form.cleaned_data["actor"])
    context = {
        "active_nav": "audit",
        "audit_logs": logs.order_by("-occurred_at", "-id")[:200],
        "filters": form,
    }
    return render(request, "staffops/audit_timeline.html", context)


@require_GET
def payment_success(request):
    return render(request, "staffops/payment_success.html", {"active_nav": ""})


@require_GET
def payment_cancel(request):
    return render(request, "staffops/payment_cancel.html", {"active_nav": ""})
