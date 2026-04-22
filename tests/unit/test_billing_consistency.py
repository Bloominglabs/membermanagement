from __future__ import annotations

from datetime import date

import pytest

from apps.billing.models import Invoice, InvoiceLine, Payment
from apps.billing.services import allocate_payment_fifo, create_checkout_session
from apps.ledger.models import JournalEntry
from apps.members.models import Client, Member
from apps.members.services import update_member_status_from_balance


def create_member(*, name: str = "Consistency Member", email: str = "consistency@example.org") -> Member:
    client = Client.objects.create(
        client_type=Client.ClientType.PERSON,
        display_name_text=name,
        email=email,
    )
    return Member.objects.create(
        client=client,
        status=Member.Status.ACTIVE,
        membership_class=Member.MembershipClass.FULL,
        voting_eligible=True,
        joined_at="2026-01-01",
    )


def create_invoice(
    member: Member,
    *,
    number: str,
    total_cents: int = 5000,
    issue_date: date = date(2026, 4, 1),
    due_date: date = date(2026, 4, 15),
    status: str = Invoice.Status.ISSUED,
) -> Invoice:
    invoice = Invoice.objects.create(
        client=member.client,
        member=member,
        invoice_type=Invoice.InvoiceType.MEMBER_DUES,
        invoice_number=number,
        issue_date=issue_date,
        due_date=due_date,
        service_period_start=issue_date,
        service_period_end=due_date,
        status=status,
        currency="usd",
        total_cents=total_cents,
        description=number,
        external_processor=Invoice.ExternalProcessor.NONE,
    )
    InvoiceLine.objects.create(
        invoice=invoice,
        line_type=InvoiceLine.LineType.DUES,
        description=number,
        quantity=1,
        unit_price_cents=total_cents,
        line_total_cents=total_cents,
        amount_cents=total_cents,
    )
    return invoice


@pytest.mark.django_db
def test_allocate_payment_fifo_rejects_draft_and_cross_client_invoices():
    member = create_member()
    other_member = create_member(name="Other Member", email="other@example.org")
    draft_invoice = create_invoice(member, number="INV-DRAFT-001", status=Invoice.Status.DRAFT)
    other_invoice = create_invoice(other_member, number="INV-OTHER-001")
    payment = Payment.objects.create(
        client=member.client,
        member=member,
        amount_cents=5000,
        payment_method=Payment.PaymentMethod.CASH,
        source_type=Payment.SourceType.DUES_PAYMENT,
        status=Payment.Status.SUCCEEDED,
    )

    with pytest.raises(ValueError, match="Draft invoices cannot be allocated"):
        allocate_payment_fifo(payment, invoices=[draft_invoice])

    with pytest.raises(ValueError, match="same client"):
        allocate_payment_fifo(payment, invoices=[other_invoice])


@pytest.mark.django_db
def test_create_checkout_session_pay_balance_uses_net_receivable_and_top_level_idempotency(settings, monkeypatch):
    settings.STRIPE_SECRET_KEY = "sk_test"
    member = create_member()
    create_invoice(member, number="INV-CHECKOUT-NET")
    Payment.objects.create(
        client=member.client,
        member=member,
        received_at="2026-04-05T00:00:00Z",
        amount_cents=2000,
        payment_method=Payment.PaymentMethod.CASH,
        source_type=Payment.SourceType.PREPAYMENT_TOPUP,
        status=Payment.Status.SUCCEEDED,
    )
    captured: dict[str, dict] = {}

    monkeypatch.setattr("apps.billing.services.stripe.Customer.create", lambda **kwargs: {"id": "cus_net"})

    def fake_checkout_create(**kwargs):
        captured["session"] = kwargs
        return {"id": "cs_net", "url": "https://stripe.test/net"}

    monkeypatch.setattr("apps.billing.services.stripe.checkout.Session.create", fake_checkout_create)

    payload = create_checkout_session(member, mode="pay_balance")

    assert payload["id"] == "cs_net"
    assert captured["session"]["line_items"][0]["price_data"]["unit_amount"] == 3000
    assert captured["session"]["idempotency_key"] == f"checkout:{member.pk}:pay_balance:3000"
    assert "options" not in captured["session"]


@pytest.mark.django_db
def test_update_member_status_from_balance_keeps_not_yet_due_member_active():
    member = create_member()
    create_invoice(
        member,
        number="INV-NOT-DUE-001",
        issue_date=date(2026, 4, 1),
        due_date=date(2026, 4, 15),
    )

    update_member_status_from_balance(member, as_of=date(2026, 4, 10))
    member.refresh_from_db()

    assert member.status == Member.Status.ACTIVE


@pytest.mark.django_db
def test_api_manual_payment_matches_staff_service_side_effects(staff_client):
    member = create_member()
    invoice = create_invoice(member, number="INV-API-MANUAL-001")

    response = staff_client.post(
        "/api/payments/manual",
        data={
            "client": member.client.pk,
            "member": member.pk,
            "received_at": "2026-04-10T00:00:00Z",
            "amount_cents": 5000,
            "currency": "usd",
            "payment_method": "CHECK",
            "source_type": "DUES_PAYMENT",
            "status": "SUCCEEDED",
            "notes": "mailed check",
            "metadata": {"source": "api"},
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    payment = Payment.objects.get(pk=response.json()["id"])
    invoice.refresh_from_db()
    member.refresh_from_db()
    assert payment.payment_method == Payment.PaymentMethod.CHECK
    assert payment.allocations.filter(invoice=invoice).exists()
    assert JournalEntry.objects.filter(source_type="payment", source_id=str(payment.pk)).exists()
    assert member.status == Member.Status.ACTIVE
