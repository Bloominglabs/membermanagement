from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

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
    stripe_reconciliation_sync,
    void_invoice,
    dues_autopay_run,
)
from apps.donations.models import Donation
from apps.expenses.models import ExpenseCategory, ExpenseImportBatch, ImportedBankTransaction
from apps.expenses.services import categorize_imported_transaction, import_expense_csv
from apps.ledger.services import render_financial_report
from apps.members.models import Client, Member
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


def _admin_changelist_url(app_label: str, model_name: str) -> str:
    return reverse(f"admin:{app_label}_{model_name}_changelist")


def _url_with_query(name: str, **params) -> str:
    query = urlencode({key: value for key, value in params.items() if value not in {"", None}}, doseq=True)
    base = reverse(f"staffops:{name}")
    return f"{base}?{query}" if query else base


def _apply_ordering(queryset, sort_value: str, ordering_map: dict[str, tuple[str, ...]], default_sort: str):
    resolved_sort = sort_value if sort_value in ordering_map else default_sort
    return queryset.order_by(*ordering_map[resolved_sort]), resolved_sort


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


def _member_query_filter(query: str) -> Q:
    return (
        Q(member_number__icontains=query)
        | Q(client__display_name_text__icontains=query)
        | Q(client__first_name__icontains=query)
        | Q(client__last_name__icontains=query)
        | Q(client__email__icontains=query)
    )


def _audit_entity_admin_url(entity_type: str, entity_id: str) -> str | None:
    entity_map = {
        "AccessAllowlistSnapshot": ("access", "accessallowlistsnapshot"),
        "AccessEvent": ("access", "accessevent"),
        "Client": ("members", "client"),
        "Donation": ("donations", "donation"),
        "Expense": ("expenses", "expense"),
        "ExpenseCategory": ("expenses", "expensecategory"),
        "ExpenseImportBatch": ("expenses", "expenseimportbatch"),
        "ImportedBankTransaction": ("expenses", "importedbanktransaction"),
        "Invoice": ("billing", "invoice"),
        "InvoiceSchedule": ("billing", "invoiceschedule"),
        "JournalEntry": ("ledger", "journalentry"),
        "JournalLine": ("ledger", "journalline"),
        "Member": ("members", "member"),
        "Payment": ("billing", "payment"),
        "RFIDCredential": ("access", "rfidcredential"),
        "WebhookEvent": ("billing", "webhookevent"),
    }
    destination = entity_map.get(entity_type)
    if not destination:
        return None
    try:
        object_id = int(entity_id)
    except (TypeError, ValueError):
        return None
    return _admin_change_url(destination[0], destination[1], object_id)


def _audit_change_summary(entry: AuditLog) -> str:
    keys = list(entry.changes.keys())
    if not keys:
        keys = sorted(set(entry.before_json.keys()) | set(entry.after_json.keys()))
    if keys:
        joined = ", ".join(keys[:5])
        suffix = " ..." if len(keys) > 5 else ""
        return f"Changed: {joined}{suffix}"
    return entry.reason or entry.message or "-"


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
        "member_queue_urls": {
            "active": _url_with_query("member-list", queue="active"),
            "past_due": _url_with_query("member-list", queue="past_due"),
            "suspended": _url_with_query("member-list", queue="suspended"),
            "autopay": _url_with_query("member-list", queue="autopay"),
            "door_access": _url_with_query("member-list", queue="door_access"),
        },
        "billing_queue_urls": {
            "overdue": _url_with_query("invoice-review", queue="overdue"),
            "unreconciled_stripe": _url_with_query("payment-review", queue="unreconciled_stripe"),
        },
        "expense_queue_urls": {
            "uncategorized": _url_with_query("expense-dashboard", queue="uncategorized"),
            "needs_reconciliation": _url_with_query("expense-dashboard", queue="needs_reconciliation"),
        },
    }
    return render(request, "staffops/home.html", context)


@staff_member_required
@require_GET
def global_search(request):
    query = request.GET.get("q", "").strip()
    members = Member.objects.none()
    clients = Client.objects.none()
    invoices = Invoice.objects.none()
    payments = Payment.objects.none()
    credentials = RFIDCredential.objects.none()

    if query:
        members = Member.objects.select_related("client").filter(_member_query_filter(query)).order_by("-updated_at", "id")[:20]
        clients = Client.objects.filter(
            Q(display_name_text__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(organization_name__icontains=query)
            | Q(email__icontains=query)
        ).order_by("display_name_text", "last_name", "first_name", "id")[:20]
        invoices = Invoice.objects.select_related("client", "member", "member__client").filter(
            Q(invoice_number__icontains=query)
            | Q(client__display_name_text__icontains=query)
            | Q(client__first_name__icontains=query)
            | Q(client__last_name__icontains=query)
            | Q(client__email__icontains=query)
            | Q(external_reference__icontains=query)
        ).order_by("-due_date", "-id")[:20]
        payments = Payment.objects.select_related("client", "member", "member__client").filter(
            Q(notes__icontains=query)
            | Q(client__display_name_text__icontains=query)
            | Q(client__first_name__icontains=query)
            | Q(client__last_name__icontains=query)
            | Q(client__email__icontains=query)
            | Q(processor_payment_id__icontains=query)
            | Q(processor_charge_id__icontains=query)
        ).order_by("-received_at", "-id")[:20]
        credentials = RFIDCredential.objects.select_related("member", "member__client").filter(
            Q(uid__icontains=query)
            | Q(label__icontains=query)
            | Q(member__member_number__icontains=query)
            | Q(member__client__display_name_text__icontains=query)
            | Q(member__client__first_name__icontains=query)
            | Q(member__client__last_name__icontains=query)
        ).order_by("uid", "id")[:20]
        if query.isdigit():
            payments = (payments | Payment.objects.select_related("client", "member", "member__client").filter(pk=int(query))).distinct()[:20]

    context = {
        "active_nav": "",
        "global_query": query,
        "members": members,
        "clients": clients,
        "invoices": invoices,
        "payments": payments,
        "credentials": credentials,
        "members_api_url": "/api/members/",
        "clients_api_url": "/api/clients/",
        "invoices_api_url": "/api/invoices/",
        "payments_api_url": "/api/payments/",
        "member_admin_url": _admin_changelist_url("members", "member"),
        "client_admin_url": _admin_changelist_url("members", "client"),
        "invoice_admin_url": _admin_changelist_url("billing", "invoice"),
        "payment_admin_url": _admin_changelist_url("billing", "payment"),
        "credential_admin_url": _admin_changelist_url("access", "rfidcredential"),
    }
    return render(request, "staffops/search.html", context)


@staff_member_required
@require_GET
def member_list(request):
    members = Member.objects.select_related("client").all()
    queue = request.GET.get("queue", "").strip()
    query = request.GET.get("query", "").strip()
    status = request.GET.get("status", "").strip()
    membership_class = request.GET.get("membership_class", "").strip()
    autopay_enabled = request.GET.get("autopay_enabled", "").strip()
    door_access_enabled = request.GET.get("door_access_enabled", "").strip()
    sort = request.GET.get("sort", "").strip()

    if queue == "active":
        members = members.filter(status=Member.Status.ACTIVE)
    elif queue == "past_due":
        members = members.filter(status=Member.Status.PAST_DUE)
    elif queue == "suspended":
        members = members.filter(status=Member.Status.SUSPENDED)
    elif queue == "autopay":
        members = members.filter(autopay_enabled=True)
    elif queue == "door_access":
        members = members.filter(door_access_enabled=True)

    if query:
        members = members.filter(_member_query_filter(query))
    if status:
        members = members.filter(status=status)
    if membership_class:
        members = members.filter(membership_class=membership_class)
    if autopay_enabled in {"0", "1"}:
        members = members.filter(autopay_enabled=autopay_enabled == "1")
    if door_access_enabled in {"0", "1"}:
        members = members.filter(door_access_enabled=door_access_enabled == "1")

    members, resolved_sort = _apply_ordering(
        members,
        sort,
        {
            "name_asc": ("client__display_name_text", "client__last_name", "client__first_name", "id"),
            "name_desc": ("-client__display_name_text", "-client__last_name", "-client__first_name", "-id"),
            "updated_desc": ("-updated_at", "-id"),
            "status_asc": ("status", "client__display_name_text", "id"),
        },
        "name_asc",
    )
    member_rows = [{"member": member, "balance": get_member_balance(member)} for member in members]
    context = {
        "active_nav": "members",
        "member_rows": member_rows,
        "query": query,
        "status_filter": status,
        "membership_class_filter": membership_class,
        "autopay_enabled_filter": autopay_enabled,
        "door_access_enabled_filter": door_access_enabled,
        "sort_filter": resolved_sort,
        "active_queue": queue,
        "member_queue_urls": {
            "active": _url_with_query("member-list", queue="active"),
            "past_due": _url_with_query("member-list", queue="past_due"),
            "suspended": _url_with_query("member-list", queue="suspended"),
            "autopay": _url_with_query("member-list", queue="autopay"),
            "door_access": _url_with_query("member-list", queue="door_access"),
        },
        "members_api_url": "/api/members/",
        "members_admin_url": _admin_changelist_url("members", "member"),
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
        "manual_payment_form": ManualPaymentForm(
            initial={
                "payment_method": Payment.PaymentMethod.CASH,
                "source_type": Payment.SourceType.DUES_PAYMENT,
            }
        ),
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
        payment_method=form.cleaned_data.get("payment_method") or Payment.PaymentMethod.CASH,
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
        "invoice_queue_urls": {
            "overdue": _url_with_query("invoice-review", queue="overdue"),
            "drafts": _url_with_query("invoice-review", status=Invoice.Status.DRAFT),
        },
        "payment_queue_urls": {
            "unreconciled_stripe": _url_with_query("payment-review", queue="unreconciled_stripe"),
            "manual": _url_with_query("payment-review", processor="", source_type=Payment.SourceType.DUES_PAYMENT),
        },
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
        result = stripe_reconciliation_sync()
        if not result.configured:
            messages.warning(request, f"Stripe is not configured; {result.pending_count} payments still need reconciliation.")
        else:
            messages.info(
                request,
                "Stripe reconciliation sync scanned "
                f"{result.scanned_count} payments, reconciled {result.reconciled_count}, "
                f"left {result.pending_count} pending, and hit {result.error_count} lookup errors.",
            )
    return redirect("staffops:billing-dashboard")


@staff_member_required
@require_GET
def invoice_review(request):
    invoices = Invoice.objects.select_related("member", "client").all()
    queue = request.GET.get("queue", "").strip()
    status = request.GET.get("status", "").strip()
    invoice_type = request.GET.get("invoice_type", "").strip()
    query = request.GET.get("query", "").strip()
    due_from = request.GET.get("due_from", "").strip()
    due_to = request.GET.get("due_to", "").strip()
    sort = request.GET.get("sort", "").strip()
    if queue == "overdue":
        invoices = invoices.exclude(status__in=[Invoice.Status.DRAFT, Invoice.Status.PAID, Invoice.Status.VOID]).filter(
            due_date__lt=timezone.localdate()
        )
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
    if due_from:
        invoices = invoices.filter(due_date__gte=due_from)
    if due_to:
        invoices = invoices.filter(due_date__lte=due_to)
    invoices, resolved_sort = _apply_ordering(
        invoices,
        sort,
        {
            "due_desc": ("-due_date", "-issue_date", "-id"),
            "due_asc": ("due_date", "issue_date", "id"),
            "total_desc": ("-total_cents", "-due_date", "-id"),
            "client_asc": ("client__display_name_text", "invoice_number", "id"),
        },
        "due_desc",
    )
    context = {
        "active_nav": "billing",
        "invoices": invoices[:100],
        "status_filter": status,
        "invoice_type_filter": invoice_type,
        "query": query,
        "due_from_filter": due_from,
        "due_to_filter": due_to,
        "sort_filter": resolved_sort,
        "active_queue": queue,
        "current_url": request.get_full_path(),
        "invoice_queue_urls": {
            "overdue": _url_with_query("invoice-review", queue="overdue"),
            "drafts": _url_with_query("invoice-review", status=Invoice.Status.DRAFT),
        },
        "invoices_api_url": "/api/invoices/",
        "invoice_admin_url": _admin_changelist_url("billing", "invoice"),
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
@require_POST
def invoice_bulk_action(request):
    action = request.POST.get("action", "").strip()
    invoice_ids = [int(invoice_id) for invoice_id in request.POST.getlist("invoice_ids") if invoice_id]
    next_url = request.POST.get("next", "").strip()
    if not invoice_ids:
        messages.error(request, "Select at least one invoice.")
    else:
        invoices = list(Invoice.objects.filter(pk__in=invoice_ids).order_by("id"))
        if action == "issue":
            for invoice in invoices:
                issue_invoice(invoice)
            messages.success(request, f"Issued {len(invoices)} invoices.")
        elif action == "void":
            for invoice in invoices:
                void_invoice(invoice)
            messages.success(request, f"Voided {len(invoices)} invoices.")
        else:
            messages.error(request, "Bulk invoice action was invalid.")
    if next_url.startswith(reverse("staffops:invoice-review")):
        return redirect(next_url)
    return redirect("staffops:invoice-review")


@staff_member_required
@require_GET
def payment_review(request):
    payments = Payment.objects.select_related("member", "client").all()
    queue = request.GET.get("queue", "").strip()
    status = request.GET.get("status", "").strip()
    source_type = request.GET.get("source_type", "").strip()
    processor = request.GET.get("processor", "").strip()
    unreconciled = request.GET.get("unreconciled", "").strip()
    received_from = request.GET.get("received_from", "").strip()
    received_to = request.GET.get("received_to", "").strip()
    sort = request.GET.get("sort", "").strip()
    if queue == "unreconciled_stripe":
        payments = payments.filter(processor=ProcessorChoices.STRIPE, processor_balance_txn_id__isnull=True)
    if status:
        payments = payments.filter(status=status)
    if source_type:
        payments = payments.filter(source_type=source_type)
    if processor:
        payments = payments.filter(processor=processor)
    if unreconciled == "1":
        payments = payments.filter(processor=ProcessorChoices.STRIPE, processor_balance_txn_id__isnull=True)
    if received_from:
        payments = payments.filter(received_at__date__gte=received_from)
    if received_to:
        payments = payments.filter(received_at__date__lte=received_to)
    payments, resolved_sort = _apply_ordering(
        payments,
        sort,
        {
            "received_desc": ("-received_at", "-id"),
            "received_asc": ("received_at", "id"),
            "amount_desc": ("-amount_cents", "-received_at", "-id"),
            "amount_asc": ("amount_cents", "received_at", "id"),
            "client_asc": ("client__display_name_text", "-received_at", "-id"),
        },
        "received_desc",
    )

    payment_rows = []
    for payment in payments[:100]:
        available_invoices = []
        if payment.member_id:
            available_invoices = list(
                Invoice.objects.filter(member=payment.member)
                .exclude(status__in=[Invoice.Status.DRAFT, Invoice.Status.VOID, Invoice.Status.PAID])
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
        "received_from_filter": received_from,
        "received_to_filter": received_to,
        "sort_filter": resolved_sort,
        "active_queue": queue,
        "payment_queue_urls": {
            "unreconciled_stripe": _url_with_query("payment-review", queue="unreconciled_stripe"),
            "manual": _url_with_query("payment-review", processor="", source_type=Payment.SourceType.DUES_PAYMENT),
        },
        "payments_api_url": "/api/payments/",
        "payment_admin_url": _admin_changelist_url("billing", "payment"),
    }
    return render(request, "staffops/payment_review.html", context)


@staff_member_required
@require_POST
def payment_allocate_action(request, payment_id: int):
    payment = get_object_or_404(Payment.objects.select_related("member"), pk=payment_id)
    invoice_ids = [int(invoice_id) for invoice_id in request.POST.getlist("invoice_ids") if invoice_id]
    invoices = list(Invoice.objects.filter(pk__in=invoice_ids).order_by("due_date", "id")) if invoice_ids else None
    try:
        result = allocate_payment_fifo(payment, invoices=invoices)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("staffops:payment-review")
    messages.success(request, f"Allocated {result.allocated_cents} cents across {len(result.invoice_numbers)} invoices.")
    return redirect("staffops:payment-review")


@staff_member_required
@require_GET
def donation_list(request):
    donations = Donation.objects.order_by("-donation_date", "-id")[:100]
    return render(
        request,
        "staffops/donation_list.html",
        {
            "active_nav": "donations",
            "donations": donations,
            "donations_api_url": "/api/donations",
            "donation_admin_url": _admin_changelist_url("donations", "donation"),
            "donation_audit_url": _url_with_query("audit-timeline", entity_type="Donation"),
        },
    )


@staff_member_required
@require_GET
def expense_dashboard(request):
    queue = request.GET.get("queue", "").strip()
    uncategorized_transactions = ImportedBankTransaction.objects.select_related("expense").filter(expense__isnull=True).order_by(
        "-posted_on", "-id"
    )
    categorized_transactions = ImportedBankTransaction.objects.select_related("expense", "expense__category").filter(
        expense__isnull=False
    ).order_by("-posted_on", "-id")
    if queue == "uncategorized":
        categorized_transactions = ImportedBankTransaction.objects.none()
    elif queue == "needs_reconciliation":
        uncategorized_transactions = ImportedBankTransaction.objects.none()
        categorized_transactions = categorized_transactions.filter(is_reconciled=False)
    context = {
        "active_nav": "expenses",
        "import_form": ExpenseImportForm(initial={"parser_key": "generic_csv"}),
        "recent_batches": ExpenseImportBatch.objects.select_related("source").order_by("-imported_at", "-id")[:20],
        "uncategorized_transactions": uncategorized_transactions[:50],
        "categorized_transactions": categorized_transactions[:50],
        "categorize_form": ExpenseCategorizeForm(),
        "active_queue": queue,
        "expense_queue_urls": {
            "uncategorized": _url_with_query("expense-dashboard", queue="uncategorized"),
            "needs_reconciliation": _url_with_query("expense-dashboard", queue="needs_reconciliation"),
        },
        "expense_batches_api_url": "/api/expenses/import-batches",
        "expense_import_admin_url": _admin_changelist_url("expenses", "expenseimportbatch"),
        "expense_transaction_admin_url": _admin_changelist_url("expenses", "importedbanktransaction"),
        "expense_rule_admin_url": _admin_changelist_url("expenses", "expensecategorizationrule"),
        "expense_rule_api_url": "/api/expense-categorization-rules/",
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
    latest_snapshot = AccessAllowlistSnapshot.objects.first()
    context = {
        "active_nav": "access",
        "latest_snapshot": latest_snapshot,
        "credentials": RFIDCredential.objects.select_related("member", "member__client").order_by("uid")[:100],
        "access_events": AccessEvent.objects.select_related("member", "member__client").order_by("-occurred_at", "-id")[:100],
        "allowlist_api_url": "/api/access/allowlist/",
        "access_events_api_url": "/api/access/events/",
        "credential_admin_url": _admin_changelist_url("access", "rfidcredential"),
        "allowlist_admin_url": _admin_changelist_url("access", "accessallowlistsnapshot"),
        "access_event_admin_url": _admin_changelist_url("access", "accessevent"),
        "credential_audit_url": _url_with_query("audit-timeline", entity_type="RFIDCredential"),
        "allowlist_audit_url": _url_with_query("audit-timeline", entity_type="AccessAllowlistSnapshot"),
        "access_event_audit_url": _url_with_query("audit-timeline", entity_type="AccessEvent"),
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
        "financial_report_api_url": f"/api/reports/financial?from={start.isoformat()}&to={end.isoformat()}",
        "member_balances_api_url": "/api/reports/member-balances",
        "invoice_review_url": _url_with_query("invoice-review", due_from=start.isoformat(), due_to=end.isoformat()),
        "payment_review_url": _url_with_query("payment-review", received_from=start.isoformat(), received_to=end.isoformat()),
        "member_review_url": reverse("staffops:member-list"),
        "donation_review_url": reverse("staffops:donation-list"),
        "expense_review_url": reverse("staffops:expense-dashboard"),
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
        if form.cleaned_data["entity_id"]:
            logs = logs.filter(entity_id=form.cleaned_data["entity_id"])
        if form.cleaned_data["action"]:
            logs = logs.filter(action=form.cleaned_data["action"])
        if form.cleaned_data["actor"]:
            logs = logs.filter(actor__icontains=form.cleaned_data["actor"])
        if form.cleaned_data["occurred_from"]:
            logs = logs.filter(occurred_at__date__gte=form.cleaned_data["occurred_from"])
        if form.cleaned_data["occurred_to"]:
            logs = logs.filter(occurred_at__date__lte=form.cleaned_data["occurred_to"])
    audit_rows = []
    for entry in logs.order_by("-occurred_at", "-id")[:200]:
        audit_rows.append(
            {
                "entry": entry,
                "entity_admin_url": _audit_entity_admin_url(entry.entity_type, entry.entity_id),
                "change_summary": _audit_change_summary(entry),
            }
        )
    context = {
        "active_nav": "audit",
        "audit_rows": audit_rows,
        "filters": form,
    }
    return render(request, "staffops/audit_timeline.html", context)


@require_GET
def payment_success(request):
    return render(request, "staffops/payment_success.html", {"active_nav": ""})


@require_GET
def payment_cancel(request):
    return render(request, "staffops/payment_cancel.html", {"active_nav": ""})
