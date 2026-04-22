from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import importlib

import pytest

from apps.billing.models import (
    Invoice,
    InvoiceLine,
    Payment,
    ProcessorChoices,
    ProcessorCustomer,
    ProcessorPaymentMethod,
)
from apps.billing.services import (
    _allocated_to_invoice_in_window,
    _member_credit_balance_as_of,
    _payment_status_from_checkout_session,
    _receivable_balance_as_of,
    allocate_payment_fifo,
    construct_stripe_event,
    create_checkout_session,
    create_setup_intent,
    dues_autopay_run,
    ensure_member_credit_charge_entry,
    ensure_member_credit_payment_entry,
    ingest_stripe_event,
    monthly_dues_close,
    reconcile_unposted_stripe_payments,
    record_manual_payment,
    sync_invoice_status,
)
from apps.common.utils import cents, daterange_month_start, json_ready
from apps.ledger.models import JournalEntry
from apps.members.models import Client, Member
from apps.members.services import get_member_balance


def create_member(
    *,
    name: str | None = None,
    email: str | None = None,
    status: str = Member.Status.ACTIVE,
    membership_class: str = Member.MembershipClass.FULL,
) -> Member:
    suffix = Client.objects.count() + 1
    client = Client.objects.create(
        client_type=Client.ClientType.PERSON,
        display_name_text=name or f"Coverage Member {suffix}",
        email=email or f"coverage-{suffix}@example.org",
    )
    return Member.objects.create(
        client=client,
        status=status,
        membership_class=membership_class,
        voting_eligible=True,
        joined_at="2026-01-01",
    )


def create_invoice(
    member: Member,
    *,
    number: str,
    issue_date: date,
    due_date: date,
    total_cents: int = 5000,
    status: str = Invoice.Status.ISSUED,
) -> Invoice:
    invoice = Invoice.objects.create(
        client=member.client,
        member=member,
        invoice_type=Invoice.InvoiceType.MEMBER_DUES,
        invoice_number=number,
        issue_date=issue_date,
        due_date=due_date,
        service_period_start=issue_date.replace(day=1),
        service_period_end=issue_date.replace(day=28),
        status=status,
        total_cents=total_cents,
        description=f"Dues {number}",
        external_processor=Invoice.ExternalProcessor.NONE,
    )
    InvoiceLine.objects.create(
        invoice=invoice,
        line_type=InvoiceLine.LineType.DUES,
        description=f"Line {number}",
        quantity=1,
        unit_price_cents=total_cents,
        line_total_cents=total_cents,
        amount_cents=total_cents,
    )
    return invoice


@pytest.mark.django_db
def test_sync_invoice_status_handles_draft_overdue_partial_and_paid():
    member = create_member()
    invoice = create_invoice(
        member,
        number="INV-STATUS-001",
        issue_date=date(2026, 4, 1),
        due_date=date(2026, 4, 15),
        status=Invoice.Status.DRAFT,
    )

    assert sync_invoice_status(invoice, as_of=date(2026, 4, 10)).status == Invoice.Status.DRAFT

    invoice.status = Invoice.Status.ISSUED
    invoice.save(update_fields=["status", "updated_at"])
    assert sync_invoice_status(invoice, as_of=date(2026, 4, 20)).status == Invoice.Status.OVERDUE

    first_payment = Payment.objects.create(
        client=member.client,
        member=member,
        received_at="2026-04-10T00:00:00Z",
        amount_cents=2500,
        payment_method=Payment.PaymentMethod.CASH,
        source_type=Payment.SourceType.DUES_PAYMENT,
        status=Payment.Status.SUCCEEDED,
    )
    allocate_payment_fifo(first_payment, invoices=[invoice])
    assert invoice.refresh_from_db() is None
    assert invoice.status == Invoice.Status.PARTIALLY_PAID

    second_payment = Payment.objects.create(
        client=member.client,
        member=member,
        received_at="2026-04-12T00:00:00Z",
        amount_cents=2500,
        payment_method=Payment.PaymentMethod.CASH,
        source_type=Payment.SourceType.DUES_PAYMENT,
        status=Payment.Status.SUCCEEDED,
    )
    allocate_payment_fifo(second_payment, invoices=[invoice])
    invoice.refresh_from_db()

    assert invoice.status == Invoice.Status.PAID


@pytest.mark.django_db
def test_member_credit_helpers_skip_memberless_entries_and_spent_payments():
    member = create_member()
    invoice = create_invoice(
        member,
        number="INV-SPENT-001",
        issue_date=date(2026, 4, 1),
        due_date=date(2026, 4, 15),
    )
    memberless_payment = Payment.objects.create(
        client=member.client,
        amount_cents=1000,
        payment_method=Payment.PaymentMethod.CASH,
        source_type=Payment.SourceType.OTHER_INCOME,
        status=Payment.Status.SUCCEEDED,
    )

    ensure_member_credit_payment_entry(memberless_payment)
    ensure_member_credit_charge_entry(memberless_payment, invoice, 1000)

    failed_payment = Payment.objects.create(
        client=member.client,
        member=member,
        amount_cents=500,
        payment_method=Payment.PaymentMethod.CASH,
        source_type=Payment.SourceType.DUES_PAYMENT,
        status=Payment.Status.FAILED,
    )
    spent_payment = Payment.objects.create(
        client=member.client,
        member=member,
        amount_cents=5000,
        payment_method=Payment.PaymentMethod.CASH,
        source_type=Payment.SourceType.DUES_PAYMENT,
        status=Payment.Status.SUCCEEDED,
    )

    first_result = allocate_payment_fifo(spent_payment, invoices=[invoice])
    second_result = allocate_payment_fifo(spent_payment, invoices=[invoice])
    failed_result = allocate_payment_fifo(failed_payment, invoices=[invoice])

    assert first_result.allocated_cents == 5000
    assert second_result.allocated_cents == 0
    assert failed_result.allocated_cents == 0


@pytest.mark.django_db
def test_allocate_payment_fifo_skips_paid_invoice_and_applies_to_next_open_invoice():
    member = create_member()
    paid_invoice = create_invoice(
        member,
        number="INV-PAID-FIRST",
        issue_date=date(2026, 4, 1),
        due_date=date(2026, 4, 15),
    )
    open_invoice = create_invoice(
        member,
        number="INV-OPEN-SECOND",
        issue_date=date(2026, 5, 1),
        due_date=date(2026, 5, 15),
    )
    paid_payment = Payment.objects.create(
        client=member.client,
        member=member,
        amount_cents=5000,
        payment_method=Payment.PaymentMethod.CASH,
        source_type=Payment.SourceType.DUES_PAYMENT,
        status=Payment.Status.SUCCEEDED,
    )
    allocate_payment_fifo(paid_payment, invoices=[paid_invoice])

    next_payment = Payment.objects.create(
        client=member.client,
        member=member,
        amount_cents=1000,
        payment_method=Payment.PaymentMethod.CASH,
        source_type=Payment.SourceType.DUES_PAYMENT,
        status=Payment.Status.SUCCEEDED,
    )
    result = allocate_payment_fifo(next_payment, invoices=[paid_invoice, open_invoice])
    paid_invoice.refresh_from_db()
    open_invoice.refresh_from_db()

    assert result.invoice_numbers == ["INV-OPEN-SECOND"]
    assert paid_invoice.status == Invoice.Status.PAID
    assert open_invoice.status == Invoice.Status.PARTIALLY_PAID


@pytest.mark.django_db
def test_monthly_dues_close_creates_for_billable_members_and_applies_credit():
    active_member = create_member(name="Active", email="active@example.org", status=Member.Status.ACTIVE)
    past_due_member = create_member(name="Past Due", email="pastdue@example.org", status=Member.Status.PAST_DUE)
    left_member = create_member(name="Left", email="left@example.org", status=Member.Status.LEFT)
    Payment.objects.create(
        client=active_member.client,
        member=active_member,
        received_at="2026-04-01T00:00:00Z",
        amount_cents=5000,
        payment_method=Payment.PaymentMethod.CASH,
        source_type=Payment.SourceType.PREPAYMENT_TOPUP,
        status=Payment.Status.SUCCEEDED,
    )

    invoices = monthly_dues_close(service_month=date(2026, 4, 1))

    assert len(invoices) == 2
    assert Invoice.objects.filter(member=left_member).count() == 0
    active_invoice = Invoice.objects.get(member=active_member)
    past_due_invoice = Invoice.objects.get(member=past_due_member)
    active_invoice.refresh_from_db()
    past_due_invoice.refresh_from_db()
    assert active_invoice.status == Invoice.Status.PAID
    assert past_due_invoice.status == Invoice.Status.ISSUED
    assert past_due_invoice.total_cents == 5000
    assert active_member.payments.get().allocations.filter(invoice=active_invoice).exists()


@pytest.mark.django_db
def test_record_manual_payment_creates_journal_entry_and_updates_balance():
    member = create_member()
    create_invoice(
        member,
        number="INV-MANUAL-001",
        issue_date=date(2026, 4, 1),
        due_date=date(2026, 4, 15),
    )

    payment = record_manual_payment(
        member=member,
        amount_cents=5000,
        source_type=Payment.SourceType.DUES_PAYMENT,
        note="front desk",
    )
    balance = get_member_balance(member, as_of=date(2026, 4, 30))

    assert payment.notes == "front desk"
    assert JournalEntry.objects.filter(source_type="payment", source_id=str(payment.pk)).exists()
    assert balance.receivable_cents == 0


@pytest.mark.django_db
def test_create_checkout_session_pay_balance_uses_existing_customer(settings, monkeypatch):
    settings.STRIPE_SECRET_KEY = "sk_test"
    member = create_member()
    create_invoice(
        member,
        number="INV-CHECKOUT-001",
        issue_date=date(2026, 4, 1),
        due_date=date(2026, 4, 15),
    )
    ProcessorCustomer.objects.create(
        processor=ProcessorChoices.STRIPE,
        processor_customer_id="cus_existing",
        client=member.client,
    )
    captured: dict[str, dict] = {}

    monkeypatch.setattr("apps.billing.services.stripe.Customer.create", lambda **kwargs: pytest.fail("unexpected customer create"))

    def fake_checkout_create(**kwargs):
        captured["session"] = kwargs
        return {"id": "cs_pay_balance", "url": "https://stripe.test/pay-balance"}

    monkeypatch.setattr("apps.billing.services.stripe.checkout.Session.create", fake_checkout_create)

    payload = create_checkout_session(member, mode="pay_balance")

    assert payload["id"] == "cs_pay_balance"
    assert captured["session"]["customer"] == "cus_existing"
    assert captured["session"]["line_items"][0]["price_data"]["unit_amount"] == 5000
    assert captured["session"]["metadata"]["source_type"] == Payment.SourceType.DUES_PAYMENT
    assert captured["session"]["idempotency_key"] == f"checkout:{member.pk}:pay_balance:5000"
    assert "options" not in captured["session"]


@pytest.mark.django_db
def test_checkout_and_setup_validation_paths(settings):
    member = create_member()

    settings.STRIPE_SECRET_KEY = ""
    with pytest.raises(ValueError, match="Stripe is not configured"):
        create_checkout_session(member, mode="top_up", amount_cents=1000)
    with pytest.raises(ValueError, match="Stripe is not configured"):
        create_setup_intent(member)
    assert dues_autopay_run() == []

    settings.STRIPE_SECRET_KEY = "sk_test"
    with pytest.raises(ValueError, match="Unsupported checkout mode"):
        create_checkout_session(member, mode="unknown")
    with pytest.raises(ValueError, match="Nothing is currently due"):
        create_checkout_session(member, mode="pay_balance")
    with pytest.raises(ValueError, match="Top-up amount must be positive"):
        create_checkout_session(member, mode="top_up", amount_cents=0)


@pytest.mark.django_db
def test_construct_event_payment_status_and_reconciliation_helpers(settings):
    settings.STRIPE_WEBHOOK_SECRET = ""
    with pytest.raises(ValueError, match="webhook secret"):
        construct_stripe_event(b"{}", "sig")

    assert _payment_status_from_checkout_session({"payment_status": "paid"}) == Payment.Status.SUCCEEDED
    assert _payment_status_from_checkout_session({"payment_status": "unpaid"}) == Payment.Status.PENDING

    member = create_member()
    Payment.objects.create(
        client=member.client,
        member=member,
        amount_cents=1000,
        payment_method=Payment.PaymentMethod.STRIPE_CARD,
        source_type=Payment.SourceType.DUES_PAYMENT,
        status=Payment.Status.SUCCEEDED,
        processor=ProcessorChoices.STRIPE,
        processor_payment_id="pi_count_1",
    )
    Payment.objects.create(
        client=member.client,
        member=member,
        amount_cents=1000,
        payment_method=Payment.PaymentMethod.STRIPE_CARD,
        source_type=Payment.SourceType.DUES_PAYMENT,
        status=Payment.Status.SUCCEEDED,
        processor=ProcessorChoices.STRIPE,
        processor_payment_id="pi_count_2",
        processor_balance_txn_id="txn_123",
    )
    Payment.objects.create(
        client=member.client,
        member=member,
        amount_cents=1000,
        payment_method=Payment.PaymentMethod.STRIPE_CARD,
        source_type=Payment.SourceType.DUES_PAYMENT,
        status=Payment.Status.FAILED,
        processor=ProcessorChoices.STRIPE,
        processor_payment_id="pi_count_3",
    )

    assert reconcile_unposted_stripe_payments() == 1


@pytest.mark.django_db
def test_dues_autopay_run_skips_members_without_needed_balance(settings, monkeypatch):
    settings.STRIPE_SECRET_KEY = "sk_test"
    member = create_member()
    payment_method = ProcessorPaymentMethod.objects.create(
        processor=ProcessorChoices.STRIPE,
        processor_payment_method_id="pm_skip",
        client=member.client,
        member=member,
        method_type=ProcessorPaymentMethod.MethodType.CARD,
        is_default=True,
    )
    member.autopay_enabled = True
    member.autopay_payment_method = payment_method
    member.default_payment_method_id = "pm_skip"
    member.save(update_fields=["autopay_enabled", "autopay_payment_method", "default_payment_method_id", "updated_at"])
    monkeypatch.setattr("apps.billing.services.stripe.PaymentIntent.create", lambda **kwargs: pytest.fail("unexpected PI create"))

    assert dues_autopay_run() == []


@pytest.mark.django_db
def test_balance_helpers_and_checkout_session_webhook_paid_branch():
    member = create_member()
    invoice = create_invoice(
        member,
        number="INV-HELPER-001",
        issue_date=date(2026, 4, 1),
        due_date=date(2026, 4, 15),
    )
    payment = Payment.objects.create(
        client=member.client,
        member=member,
        received_at="2026-04-05T00:00:00Z",
        amount_cents=7000,
        payment_method=Payment.PaymentMethod.CASH,
        source_type=Payment.SourceType.PREPAYMENT_TOPUP,
        status=Payment.Status.SUCCEEDED,
    )
    allocate_payment_fifo(payment, invoices=[invoice])

    assert _receivable_balance_as_of(date(2026, 4, 30)) == 0
    assert _member_credit_balance_as_of(date(2026, 4, 30)) == 2000
    assert _member_credit_balance_as_of(date(2026, 4, 2)) == 0
    assert _allocated_to_invoice_in_window(invoice, date(2026, 4, 1), date(2026, 4, 30)) == 5000


@pytest.mark.django_db
def test_ingest_checkout_session_completed_paid_creates_succeeded_payment():
    member = create_member()
    invoice = create_invoice(
        member,
        number="INV-CHECKOUT-WEBHOOK-001",
        issue_date=date(2026, 4, 1),
        due_date=date(2026, 4, 15),
    )
    event = {
        "id": "evt_checkout_paid_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_paid_1",
                "payment_intent": "pi_checkout_paid_1",
                "created": 1710000000,
                "payment_status": "paid",
                "amount_total": 5000,
                "currency": "usd",
                "metadata": {
                    "member_id": str(member.pk),
                    "client_id": str(member.client_id),
                    "source_type": Payment.SourceType.DUES_PAYMENT,
                },
            }
        },
    }

    ingest_stripe_event(event)
    payment = Payment.objects.get(processor_payment_id="pi_checkout_paid_1")
    invoice.refresh_from_db()

    assert payment.status == Payment.Status.SUCCEEDED
    assert invoice.status == Invoice.Status.PAID


@pytest.mark.django_db
def test_client_alias_properties_common_utils_and_entrypoint_imports():
    client = Client.objects.create(
        client_type=Client.ClientType.PERSON,
        first_name="Pat",
        last_name="Maker",
        email="pat@example.org",
    )
    client.primary_email = "pat.maker@example.org"
    client.primary_phone = "555-0101"
    client.address_line1 = "123 Main"
    client.address_line2 = "Suite B"
    client.save()

    assert client.display_name == "Pat Maker"
    assert client.primary_email == "pat.maker@example.org"
    assert client.primary_phone == "555-0101"
    assert client.address_line1 == "123 Main"
    assert client.address_line2 == "Suite B"
    assert cents(Decimal("12.34")) == 1234
    assert daterange_month_start(date(2026, 4, 19)) == date(2026, 4, 1)

    @dataclass
    class Payload:
        when: date
        values: tuple[int, int]

    assert json_ready(Payload(when=date(2026, 4, 19), values=(1, 2))) == {
        "when": "2026-04-19",
        "values": [1, 2],
    }

    asgi = importlib.import_module("config.asgi")
    wsgi = importlib.import_module("config.wsgi")

    assert hasattr(asgi, "application")
    assert hasattr(wsgi, "application")
