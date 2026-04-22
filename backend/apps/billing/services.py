from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone as dt_timezone

import stripe
from django.conf import settings
from django.db import transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.billing.models import (
    Allocation,
    Invoice,
    InvoiceLine,
    InvoiceSchedule,
    MemberCreditLedger,
    Payment,
    ProcessorChoices,
    ProcessorCustomer,
    ProcessorPaymentMethod,
    WebhookEvent,
)
from apps.members.models import Client, Member
from apps.members.services import get_member_balance, update_member_status_from_balance


@dataclass(slots=True)
class AllocationResult:
    allocated_cents: int
    invoice_numbers: list[str]


def calculate_due_date(issue_date: date, *, due_day: int | None = None, due_offset_days: int | None = None) -> date:
    if due_offset_days is not None:
        return issue_date + timedelta(days=due_offset_days)
    if due_day is not None:
        return issue_date.replace(day=min(due_day, 28))
    return issue_date.replace(day=min(settings.DUES_DUE_DAY, 28))


def stripe_configured() -> bool:
    return bool(settings.STRIPE_SECRET_KEY)


def invoice_paid_cents(invoice: Invoice) -> int:
    paid = invoice.allocations.filter(payment__status=Payment.Status.SUCCEEDED).aggregate(
        total=Coalesce(Sum("allocated_cents"), 0)
    )
    return paid.get("total", 0)


def invoice_outstanding_cents(invoice: Invoice) -> int:
    return max(invoice.total_cents - invoice_paid_cents(invoice), 0)


def available_payment_balance_cents(payment: Payment) -> int:
    allocated = payment.allocations.aggregate(total=Coalesce(Sum("allocated_cents"), 0)).get("total", 0)
    return max(payment.amount_cents - allocated, 0)


def sync_invoice_status(invoice: Invoice, as_of: date | None = None) -> Invoice:
    as_of = as_of or timezone.localdate()
    outstanding = invoice_outstanding_cents(invoice)
    if outstanding == 0:
        status = Invoice.Status.PAID
    elif outstanding < invoice.total_cents:
        status = Invoice.Status.PARTIALLY_PAID
    elif invoice.due_date < as_of:
        status = Invoice.Status.OVERDUE
    elif invoice.status == Invoice.Status.DRAFT:
        status = Invoice.Status.DRAFT
    else:
        status = Invoice.Status.ISSUED
    if invoice.status != status:
        invoice.status = status
        invoice.save(update_fields=["status", "updated_at"])
    return invoice


def ensure_member_credit_payment_entry(payment: Payment) -> None:
    if not payment.member:
        return
    MemberCreditLedger.objects.get_or_create(
        member=payment.member,
        entry_type=MemberCreditLedger.EntryType.PAYMENT_IN,
        reference_type="payment",
        reference_id=str(payment.pk),
        defaults={
            "delta_cents": payment.amount_cents,
            "effective_at": payment.received_at,
            "memo": payment.get_source_type_display(),
        },
    )


def ensure_member_credit_charge_entry(payment: Payment, invoice: Invoice, amount_cents: int) -> None:
    if not payment.member:
        return
    MemberCreditLedger.objects.get_or_create(
        member=payment.member,
        entry_type=MemberCreditLedger.EntryType.CHARGE_OUT,
        reference_type="allocation",
        reference_id=f"{payment.pk}:{invoice.pk}",
        defaults={
            "delta_cents": -amount_cents,
            "effective_at": timezone.now(),
            "memo": f"Applied to {invoice.invoice_number}",
        },
    )


def _default_invoices_for_payment(payment: Payment) -> list[Invoice]:
    invoices = Invoice.objects.filter(client=payment.client).exclude(
        status__in=[Invoice.Status.DRAFT, Invoice.Status.VOID]
    )
    if payment.member_id:
        invoices = invoices.filter(Q(member=payment.member) | Q(member__isnull=True))
    else:
        invoices = invoices.filter(member__isnull=True)
    return list(invoices.order_by("due_date", "issue_date", "id"))


def _validate_allocatable_invoice(payment: Payment, invoice: Invoice) -> None:
    if invoice.client_id != payment.client_id:
        raise ValueError("Payments can only be allocated to invoices for the same client.")
    if invoice.status == Invoice.Status.DRAFT:
        raise ValueError("Draft invoices cannot be allocated.")
    if invoice.status == Invoice.Status.VOID:
        raise ValueError("Void invoices cannot be allocated.")
    if payment.member_id and invoice.member_id and invoice.member_id != payment.member_id:
        raise ValueError("Payments can only be allocated to invoices for the same member or client.")


@transaction.atomic
def allocate_payment_fifo(payment: Payment, invoices: list[Invoice] | None = None) -> AllocationResult:
    if payment.status != Payment.Status.SUCCEEDED:
        return AllocationResult(allocated_cents=0, invoice_numbers=[])

    ensure_member_credit_payment_entry(payment)
    remaining = available_payment_balance_cents(payment)
    if remaining <= 0:
        return AllocationResult(allocated_cents=0, invoice_numbers=[])

    if invoices is None:
        invoices = _default_invoices_for_payment(payment)
    else:
        for invoice in invoices:
            _validate_allocatable_invoice(payment, invoice)
        invoices = sorted(invoices, key=lambda invoice: (invoice.due_date, invoice.issue_date, invoice.id))

    touched: list[str] = []
    allocated_total = 0
    for invoice in invoices:
        outstanding = invoice_outstanding_cents(invoice)
        if outstanding <= 0:
            sync_invoice_status(invoice)
            continue
        apply_cents = min(outstanding, remaining)
        if apply_cents <= 0:
            break
        Allocation.objects.create(payment=payment, invoice=invoice, allocated_cents=apply_cents)
        ensure_member_credit_charge_entry(payment, invoice, apply_cents)
        touched.append(invoice.invoice_number)
        allocated_total += apply_cents
        remaining -= apply_cents
        sync_invoice_status(invoice)
        if remaining == 0:
            break
    return AllocationResult(allocated_cents=allocated_total, invoice_numbers=touched)


def _invoice_number_for_member(member: Member, service_month: date) -> str:
    return f"DUES-{service_month:%Y%m}-{member.pk:04d}"


@transaction.atomic
def create_monthly_dues_invoice(member: Member, service_month: date | None = None) -> Invoice:
    service_month = (service_month or timezone.localdate()).replace(day=1)
    due_date = calculate_due_date(service_month, due_day=settings.DUES_DUE_DAY)
    description = f"{member.get_membership_class_display()} membership dues for {service_month:%B %Y}"
    invoice_number = _invoice_number_for_member(member, service_month)
    defaults = {
        "client": member.client,
        "member": member,
        "invoice_type": Invoice.InvoiceType.MEMBER_DUES,
        "issue_date": service_month,
        "due_date": due_date,
        "service_period_start": service_month,
        "service_period_end": (service_month + timedelta(days=32)).replace(day=1) - timedelta(days=1),
        "description": description,
        "currency": settings.STRIPE_PRICE_CURRENCY,
        "total_cents": member.dues_amount_cents(),
        "status": Invoice.Status.ISSUED,
        "external_processor": Invoice.ExternalProcessor.NONE,
        "metadata": {"kind": "monthly_dues"},
    }
    invoice, created = Invoice.objects.get_or_create(invoice_number=invoice_number, defaults=defaults)
    if created:
        InvoiceLine.objects.create(
            invoice=invoice,
            line_type=InvoiceLine.LineType.DUES,
            description=description,
            quantity=1,
            unit_price_cents=invoice.total_cents,
            line_total_cents=invoice.total_cents,
            amount_cents=invoice.total_cents,
            service_period_start=invoice.service_period_start,
            service_period_end=invoice.service_period_end,
        )
        from apps.ledger.services import post_dues_invoice

        post_dues_invoice(invoice)
        return invoice
    return sync_invoice_status(invoice)


@transaction.atomic
def generate_invoice_from_schedule(schedule: InvoiceSchedule, issue_date: date | None = None) -> Invoice:
    issue_date = issue_date or timezone.localdate()
    due_date = calculate_due_date(issue_date, due_day=schedule.due_day, due_offset_days=schedule.due_offset_days)
    invoice_number = f"SCH-{schedule.pk}-{issue_date:%Y%m%d}"
    invoice, created = Invoice.objects.get_or_create(
        invoice_number=invoice_number,
        defaults={
            "client": schedule.client,
            "member": schedule.member,
            "invoice_type": schedule.invoice_type,
            "issue_date": issue_date,
            "due_date": due_date,
            "service_period_start": issue_date,
            "service_period_end": due_date,
            "status": Invoice.Status.ISSUED,
            "currency": settings.STRIPE_PRICE_CURRENCY,
            "total_cents": schedule.amount_cents,
            "description": schedule.description,
            "notes": schedule.description,
            "external_processor": Invoice.ExternalProcessor.NONE,
            "metadata": {"schedule_id": schedule.pk},
        },
    )
    if created:
        InvoiceLine.objects.create(
            invoice=invoice,
            line_type=InvoiceLine.LineType.OTHER,
            description=schedule.description,
            quantity=1,
            unit_price_cents=schedule.amount_cents,
            line_total_cents=schedule.amount_cents,
            amount_cents=schedule.amount_cents,
            service_period_start=issue_date,
            service_period_end=due_date,
        )
        schedule.last_issued_on = issue_date
        schedule.save(update_fields=["last_issued_on"])
    return invoice


def _period_start_for_schedule(schedule: InvoiceSchedule, run_date: date) -> date:
    if schedule.frequency == InvoiceSchedule.Frequency.QUARTERLY:
        start_month = ((run_date.month - 1) // 3) * 3 + 1
        return date(run_date.year, start_month, 1)
    if schedule.frequency == InvoiceSchedule.Frequency.ANNUAL:
        return date(run_date.year, 1, 1)
    if schedule.frequency == InvoiceSchedule.Frequency.ONE_OFF:
        created_on = timezone.localtime(schedule.created_at).date() if timezone.is_aware(schedule.created_at) else schedule.created_at.date()
        return created_on.replace(day=1)
    return run_date.replace(day=1)


def _scheduled_issue_date_for_period(schedule: InvoiceSchedule, run_date: date) -> date:
    period_start = _period_start_for_schedule(schedule, run_date)
    default_day = run_date.day if schedule.frequency == InvoiceSchedule.Frequency.ONE_OFF else 1
    generation_day = min(schedule.generation_day or default_day, 28)
    return period_start.replace(day=generation_day)


def _already_issued_for_period(schedule: InvoiceSchedule, issue_date: date) -> bool:
    if not schedule.last_issued_on:
        return False
    if schedule.frequency == InvoiceSchedule.Frequency.ONE_OFF:
        return True
    if schedule.frequency == InvoiceSchedule.Frequency.ANNUAL:
        return schedule.last_issued_on.year == issue_date.year
    if schedule.frequency == InvoiceSchedule.Frequency.QUARTERLY:
        current_quarter = (issue_date.month - 1) // 3
        issued_quarter = (schedule.last_issued_on.month - 1) // 3
        return schedule.last_issued_on.year == issue_date.year and issued_quarter == current_quarter
    return schedule.last_issued_on.year == issue_date.year and schedule.last_issued_on.month == issue_date.month


@transaction.atomic
def generate_due_scheduled_invoices(run_date: date | None = None) -> list[Invoice]:
    run_date = run_date or timezone.localdate()
    invoices: list[Invoice] = []
    schedules = InvoiceSchedule.objects.filter(active=True).select_related("client", "member").order_by("id")
    for schedule in schedules:
        issue_date = _scheduled_issue_date_for_period(schedule, run_date)
        if run_date < issue_date:
            continue
        if _already_issued_for_period(schedule, issue_date):
            continue
        invoices.append(generate_invoice_from_schedule(schedule, issue_date=issue_date))
    return invoices


@transaction.atomic
def create_one_off_invoice(
    *,
    member: Member,
    invoice_number: str,
    description: str,
    amount_cents: int,
    issue_date: date | None = None,
    due_date: date | None = None,
    due_day: int | None = None,
    due_offset_days: int | None = None,
) -> Invoice:
    issue_date = issue_date or timezone.localdate()
    resolved_due_date = due_date or calculate_due_date(issue_date, due_day=due_day, due_offset_days=due_offset_days)
    invoice = Invoice.objects.create(
        client=member.client,
        member=member,
        invoice_type=Invoice.InvoiceType.ONE_OFF,
        invoice_number=invoice_number,
        issue_date=issue_date,
        due_date=resolved_due_date,
        service_period_start=issue_date,
        service_period_end=resolved_due_date,
        status=Invoice.Status.ISSUED,
        currency=settings.STRIPE_PRICE_CURRENCY,
        total_cents=amount_cents,
        description=description,
        notes=description,
        external_processor=Invoice.ExternalProcessor.NONE,
        metadata={"kind": "staff_one_off"},
    )
    InvoiceLine.objects.create(
        invoice=invoice,
        line_type=InvoiceLine.LineType.OTHER,
        description=description,
        quantity=1,
        unit_price_cents=amount_cents,
        line_total_cents=amount_cents,
        amount_cents=amount_cents,
        service_period_start=issue_date,
        service_period_end=resolved_due_date,
    )
    return invoice


@transaction.atomic
def monthly_dues_close(service_month: date | None = None) -> list[Invoice]:
    invoices: list[Invoice] = []
    members = Member.objects.filter(status__in=[Member.Status.ACTIVE, Member.Status.PAST_DUE]).select_related("client")
    for member in members:
        invoice = create_monthly_dues_invoice(member, service_month=service_month)
        invoices.append(invoice)
        # Monthly close should consume prepaid credit, not guess how to re-route every historical payment.
        for payment in member.payments.filter(
            status=Payment.Status.SUCCEEDED,
            source_type=Payment.SourceType.PREPAYMENT_TOPUP,
        ).order_by("received_at", "id"):
            if available_payment_balance_cents(payment) > 0:
                allocate_payment_fifo(payment)
        update_member_status_from_balance(member)
    return invoices


@transaction.atomic
def record_manual_payment(
    member: Member | None,
    amount_cents: int,
    *,
    client: Client | None = None,
    payment_method: str = Payment.PaymentMethod.OTHER,
    source_type: str = Payment.SourceType.OTHER_INCOME,
    note: str = "",
    currency: str | None = None,
    received_at: datetime | None = None,
    status: str = Payment.Status.SUCCEEDED,
    metadata: dict | None = None,
) -> Payment:
    resolved_client = client or (member.client if member else None)
    if resolved_client is None:
        raise ValueError("Manual payments require a client or member.")
    if member and member.client_id != resolved_client.pk:
        raise ValueError("Manual payments must use the member's client.")

    payment = Payment.objects.create(
        client=resolved_client,
        member=member,
        received_at=received_at or timezone.now(),
        amount_cents=amount_cents,
        currency=currency or settings.STRIPE_PRICE_CURRENCY,
        source_type=source_type,
        payment_method=payment_method,
        status=status,
        notes=note,
        metadata=metadata or {},
    )
    if payment.status == Payment.Status.SUCCEEDED:
        allocate_payment_fifo(payment)
        from apps.ledger.services import post_payment

        post_payment(payment)
        if payment.member:
            update_member_status_from_balance(payment.member)
    return payment


def _get_or_create_stripe_customer(member: Member) -> ProcessorCustomer:
    stripe.api_key = settings.STRIPE_SECRET_KEY
    customer = ProcessorCustomer.objects.filter(
        processor=ProcessorChoices.STRIPE, client=member.client
    ).first()
    if customer:
        return customer
    remote_customer = stripe.Customer.create(
        email=member.client.email,
        name=member.client.display_name,
        metadata={"member_id": member.pk, "client_id": member.client_id},
    )
    Member.objects.filter(pk=member.pk).update(stripe_customer_id=remote_customer["id"])
    return ProcessorCustomer.objects.create(
        processor=ProcessorChoices.STRIPE,
        processor_customer_id=remote_customer["id"],
        client=member.client,
    )


def create_checkout_session(
    member: Member,
    mode: str,
    amount_cents: int | None = None,
    success_url: str | None = None,
    cancel_url: str | None = None,
) -> dict:
    if not stripe_configured():
        raise ValueError("Stripe is not configured.")

    balance = get_member_balance(member)
    if mode == "pay_balance":
        # A member should only be asked to pay the receivable that is still uncovered by prior credit.
        amount_cents = max(balance.receivable_cents - balance.credit_cents, 0)
        source_type = Payment.SourceType.DUES_PAYMENT
    elif mode == "top_up":
        if not amount_cents or amount_cents <= 0:
            raise ValueError("Top-up amount must be positive.")
        source_type = Payment.SourceType.PREPAYMENT_TOPUP
    else:
        raise ValueError("Unsupported checkout mode.")

    if not amount_cents or amount_cents <= 0:
        raise ValueError("Nothing is currently due.")

    stripe.api_key = settings.STRIPE_SECRET_KEY
    customer = _get_or_create_stripe_customer(member)
    metadata = {
        "member_id": str(member.pk),
        "client_id": str(member.client_id),
        "purpose": mode,
        "source_type": source_type,
    }
    idempotency_key = f"checkout:{member.pk}:{mode}:{amount_cents}"
    session = stripe.checkout.Session.create(
        customer=customer.processor_customer_id,
        client_reference_id=str(member.pk),
        success_url=success_url or settings.FRONTEND_SUCCESS_URL,
        cancel_url=cancel_url or settings.FRONTEND_CANCEL_URL,
        metadata=metadata,
        line_items=[
            {
                "quantity": 1,
                "price_data": {
                    "currency": settings.STRIPE_PRICE_CURRENCY,
                    "unit_amount": amount_cents,
                    "product_data": {
                        "name": "Bloominglabs dues payment" if mode == "pay_balance" else "Bloominglabs credit top-up"
                    },
                },
            }
        ],
        mode="payment",
        payment_intent_data={"metadata": metadata},
        idempotency_key=idempotency_key,
    )
    return dict(session)


def create_setup_intent(member: Member) -> dict:
    if not stripe_configured():
        raise ValueError("Stripe is not configured.")
    stripe.api_key = settings.STRIPE_SECRET_KEY
    customer = _get_or_create_stripe_customer(member)
    setup_intent = stripe.SetupIntent.create(
        customer=customer.processor_customer_id,
        payment_method_types=["card", "us_bank_account"],
        metadata={"member_id": member.pk, "client_id": member.client_id},
        usage="off_session",
    )
    return dict(setup_intent)


def construct_stripe_event(payload: bytes, signature_header: str) -> dict:
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise ValueError("Stripe webhook secret is not configured.")
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe.Webhook.construct_event(payload=payload, sig_header=signature_header, secret=settings.STRIPE_WEBHOOK_SECRET)


def _source_type_from_metadata(metadata: dict) -> str:
    return metadata.get("source_type") or (
        Payment.SourceType.PREPAYMENT_TOPUP if metadata.get("purpose") == "top_up" else Payment.SourceType.DUES_PAYMENT
    )


def _payment_status_from_checkout_session(session: dict) -> str:
    if session.get("payment_status") == "paid":
        return Payment.Status.SUCCEEDED
    return Payment.Status.PENDING


@transaction.atomic
def _upsert_payment_from_stripe_object(payload: dict, status: str, source_type: str) -> Payment:
    metadata = payload.get("metadata") or {}
    member = Member.objects.select_related("client").get(pk=metadata["member_id"])
    payment_intent_id = payload.get("payment_intent") or payload.get("id")
    defaults = {
        "client": member.client,
        "member": member,
        "received_at": datetime.fromtimestamp(payload.get("created", timezone.now().timestamp()), tz=dt_timezone.utc),
        "amount_cents": payload.get("amount_received") or payload.get("amount_total") or payload.get("amount") or 0,
        "currency": payload.get("currency", settings.STRIPE_PRICE_CURRENCY),
        "source_type": source_type,
        "status": status,
        "payment_method": Payment.PaymentMethod.STRIPE_ACH if payload.get("payment_method_types") == ["us_bank_account"] else Payment.PaymentMethod.STRIPE_CARD,
        "processor_event_id": metadata.get("event_id"),
        "processor_charge_id": payload.get("latest_charge") or payload.get("id"),
        "metadata": metadata,
    }
    payment, _ = Payment.objects.update_or_create(
        processor=ProcessorChoices.STRIPE,
        processor_payment_id=payment_intent_id,
        defaults=defaults,
    )
    return payment


@transaction.atomic
def ingest_stripe_event(event: dict) -> WebhookEvent:
    webhook_event, created = WebhookEvent.objects.get_or_create(
        processor=ProcessorChoices.STRIPE,
        event_id=event["id"],
        defaults={"payload_json": event, "signature_valid": True},
    )
    if not created and webhook_event.processed_at:
        return webhook_event

    webhook_event.payload_json = event
    webhook_event.signature_valid = True
    event_type = event["type"]
    obj = event["data"]["object"]

    if event_type == "checkout.session.completed":
        payment = _upsert_payment_from_stripe_object(
            obj,
            status=_payment_status_from_checkout_session(obj),
            source_type=_source_type_from_metadata(obj.get("metadata") or {}),
        )
        if payment.status == Payment.Status.SUCCEEDED:
            allocate_payment_fifo(payment)
            from apps.ledger.services import post_payment

            post_payment(payment)
            update_member_status_from_balance(payment.member)
    elif event_type == "payment_intent.succeeded":
        payment = _upsert_payment_from_stripe_object(
            obj,
            status=Payment.Status.SUCCEEDED,
            source_type=_source_type_from_metadata(obj.get("metadata") or {}),
        )
        allocate_payment_fifo(payment)
        from apps.ledger.services import post_payment

        post_payment(payment)
        update_member_status_from_balance(payment.member)
    elif event_type == "payment_intent.payment_failed":
        _upsert_payment_from_stripe_object(
            obj,
            status=Payment.Status.FAILED,
            source_type=_source_type_from_metadata(obj.get("metadata") or {}),
        )
    elif event_type == "setup_intent.succeeded":
        metadata = obj.get("metadata") or {}
        member = Member.objects.select_related("client").get(pk=metadata["member_id"])
        payment_method, _ = ProcessorPaymentMethod.objects.update_or_create(
            processor=ProcessorChoices.STRIPE,
            processor_payment_method_id=obj["payment_method"],
            defaults={
                "client": member.client,
                "member": member,
                "method_type": ProcessorPaymentMethod.MethodType.ACH
                if "us_bank_account" in (obj.get("payment_method_types") or [])
                else ProcessorPaymentMethod.MethodType.CARD,
                "is_default": True,
            },
        )
        ProcessorPaymentMethod.objects.filter(
            member=member,
            processor=ProcessorChoices.STRIPE,
        ).exclude(pk=payment_method.pk).update(is_default=False)
        member.autopay_enabled = True
        member.default_payment_method_id = obj["payment_method"]
        member.autopay_payment_method = payment_method
        member.save(
            update_fields=[
                "autopay_enabled",
                "default_payment_method_id",
                "autopay_payment_method",
                "updated_at",
            ]
        )
    webhook_event.processed_at = timezone.now()
    webhook_event.save(update_fields=["payload_json", "signature_valid", "processed_at"])
    return webhook_event


def reconcile_unposted_stripe_payments() -> int:
    return Payment.objects.filter(
        processor=ProcessorChoices.STRIPE,
        status=Payment.Status.SUCCEEDED,
        processor_balance_txn_id__isnull=True,
    ).count()


def dues_autopay_run() -> list[dict]:
    if not stripe_configured():
        return []

    stripe.api_key = settings.STRIPE_SECRET_KEY
    results: list[dict] = []
    members = Member.objects.filter(
        autopay_enabled=True,
        status__in=[Member.Status.ACTIVE, Member.Status.PAST_DUE],
        autopay_payment_method__isnull=False,
    ).select_related("client", "autopay_payment_method")
    for member in members:
        balance = get_member_balance(member)
        needed_cents = max(balance.receivable_cents - balance.credit_cents, 0)
        if needed_cents <= 0:
            continue
        customer = _get_or_create_stripe_customer(member)
        payment_intent = stripe.PaymentIntent.create(
            amount=needed_cents,
            currency=settings.STRIPE_PRICE_CURRENCY,
            customer=customer.processor_customer_id,
            payment_method=member.autopay_payment_method.processor_payment_method_id,
            off_session=True,
            confirm=True,
            metadata={
                "member_id": str(member.pk),
                "client_id": str(member.client_id),
                "source_type": Payment.SourceType.DUES_PAYMENT,
                "purpose": "autopay",
            },
            idempotency_key=f"autopay:{member.pk}:{timezone.localdate().isoformat()}:{needed_cents}",
        )
        results.append({"member_id": member.pk, "payment_intent_id": payment_intent.get("id"), "amount_cents": needed_cents})
    return results


@transaction.atomic
def issue_invoice(invoice: Invoice) -> Invoice:
    invoice.status = Invoice.Status.ISSUED if invoice.status != Invoice.Status.VOID else Invoice.Status.VOID
    invoice.save(update_fields=["status", "updated_at"])
    return invoice


@transaction.atomic
def void_invoice(invoice: Invoice) -> Invoice:
    invoice.status = Invoice.Status.VOID
    invoice.save(update_fields=["status", "updated_at"])
    return invoice


def _allocated_to_invoice_in_window(invoice: Invoice, start: date, end: date) -> int:
    return (
        invoice.allocations.filter(
            payment__status=Payment.Status.SUCCEEDED,
            payment__received_at__date__gte=start,
            payment__received_at__date__lte=end,
        ).aggregate(total=Coalesce(Sum("allocated_cents"), 0)).get("total", 0)
    )


def _member_credit_balance_as_of(as_of: date) -> int:
    credits = 0
    for payment in Payment.objects.filter(status=Payment.Status.SUCCEEDED, received_at__date__lte=as_of):
        applied = payment.allocations.filter(allocated_at__date__lte=as_of).aggregate(total=Coalesce(Sum("allocated_cents"), 0)).get("total", 0)
        credits += max(payment.amount_cents - applied, 0)
    return credits


def _receivable_balance_as_of(as_of: date) -> int:
    total = 0
    for invoice in Invoice.objects.exclude(status=Invoice.Status.VOID).filter(issue_date__lte=as_of):
        paid = invoice.allocations.filter(
            payment__status=Payment.Status.SUCCEEDED,
            allocated_at__date__lte=as_of,
        ).aggregate(total=Coalesce(Sum("allocated_cents"), 0)).get("total", 0)
        total += max(invoice.total_cents - paid, 0)
    return total


def build_ar_aging_report(as_of: date | None = None) -> dict[str, int | dict[str, int]]:
    as_of = as_of or timezone.localdate()
    buckets = {"current": 0, "1_30": 0, "31_60": 0, "61_90": 0, "over_90": 0}
    total = 0
    for invoice in Invoice.objects.exclude(status=Invoice.Status.VOID):
        outstanding = max(
            invoice.total_cents
            - sum(allocation.allocated_cents for allocation in invoice.allocations.filter(payment__status=Payment.Status.SUCCEEDED)),
            0,
        )
        if outstanding <= 0:
            continue
        total += outstanding
        days_past_due = (as_of - invoice.due_date).days
        if days_past_due <= 0:
            buckets["current"] += outstanding
        elif days_past_due <= 30:
            buckets["1_30"] += outstanding
        elif days_past_due <= 60:
            buckets["31_60"] += outstanding
        elif days_past_due <= 90:
            buckets["61_90"] += outstanding
        else:
            buckets["over_90"] += outstanding
    return {"total_receivables_cents": total, "buckets": buckets}
