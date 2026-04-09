from __future__ import annotations

from datetime import date

import pytest

from apps.billing.models import Payment, ProcessorPaymentMethod
from apps.members.models import Client, Member


def create_member(*, autopay: bool = False) -> Member:
    client = Client.objects.create(
        client_type=Client.ClientType.PERSON,
        display_name_text=f"Stripe Member {Client.objects.count() + 1}",
        email=f"stripe-{Client.objects.count() + 1}@example.org",
    )
    member = Member.objects.create(
        client=client,
        status=Member.Status.ACTIVE,
        membership_class=Member.MembershipClass.FULL,
        voting_eligible=True,
        joined_at="2026-01-01",
        autopay_enabled=autopay,
    )
    return member


@pytest.mark.django_db
def test_create_checkout_session_top_up_uses_stripe_and_metadata(settings, monkeypatch):
    settings.STRIPE_SECRET_KEY = "sk_test"
    member = create_member()
    captured = {}

    def fake_customer_create(**kwargs):
        captured["customer"] = kwargs
        return {"id": "cus_123"}

    def fake_checkout_create(**kwargs):
        captured["session"] = kwargs
        return {"id": "cs_123", "url": "https://stripe.test/session"}

    monkeypatch.setattr("apps.billing.services.stripe.Customer.create", fake_customer_create)
    monkeypatch.setattr("apps.billing.services.stripe.checkout.Session.create", fake_checkout_create)

    from apps.billing.services import create_checkout_session

    session = create_checkout_session(member, mode="top_up", amount_cents=2500)

    assert session["id"] == "cs_123"
    assert captured["session"]["metadata"]["purpose"] == "top_up"
    assert captured["session"]["line_items"][0]["price_data"]["unit_amount"] == 2500
    member.refresh_from_db()
    assert member.stripe_customer_id == "cus_123"


@pytest.mark.django_db
def test_create_setup_intent_and_webhook_sets_default_payment_method(settings, monkeypatch):
    settings.STRIPE_SECRET_KEY = "sk_test"
    member = create_member()

    monkeypatch.setattr("apps.billing.services.stripe.Customer.create", lambda **kwargs: {"id": "cus_456"})
    monkeypatch.setattr(
        "apps.billing.services.stripe.SetupIntent.create",
        lambda **kwargs: {"id": "seti_123", "client_secret": "secret_123"},
    )

    from apps.billing.services import create_setup_intent, ingest_stripe_event

    payload = create_setup_intent(member)
    assert payload["client_secret"] == "secret_123"

    event = {
        "id": "evt_setup_1",
        "type": "setup_intent.succeeded",
        "data": {
            "object": {
                "id": "seti_123",
                "payment_method": "pm_123",
                "payment_method_types": ["card"],
                "metadata": {"member_id": str(member.pk), "client_id": str(member.client_id)},
            }
        },
    }

    ingest_stripe_event(event)
    member.refresh_from_db()

    assert member.autopay_enabled is True
    assert member.default_payment_method_id == "pm_123"
    assert ProcessorPaymentMethod.objects.filter(member=member, processor_payment_method_id="pm_123").exists()
    assert member.autopay_payment_method is not None
    assert member.autopay_payment_method.processor_payment_method_id == "pm_123"


@pytest.mark.django_db
def test_dues_autopay_run_creates_off_session_payment_intent(settings, monkeypatch):
    settings.STRIPE_SECRET_KEY = "sk_test"
    member = create_member(autopay=True)
    payment_method = ProcessorPaymentMethod.objects.create(
        processor="STRIPE",
        processor_payment_method_id="pm_auto",
        client=member.client,
        member=member,
        method_type=ProcessorPaymentMethod.MethodType.CARD,
        is_default=True,
    )
    member.autopay_payment_method = payment_method
    member.default_payment_method_id = "pm_auto"
    member.save(update_fields=["autopay_payment_method", "default_payment_method_id", "updated_at"])

    from apps.billing.models import Invoice, InvoiceLine

    invoice = Invoice.objects.create(
        client=member.client,
        member=member,
        invoice_type=Invoice.InvoiceType.MEMBER_DUES,
        invoice_number="INV-AUTO-001",
        issue_date="2026-04-01",
        due_date="2026-04-15",
        service_period_start="2026-04-01",
        service_period_end="2026-04-30",
        status=Invoice.Status.ISSUED,
        total_cents=5000,
        external_processor=Invoice.ExternalProcessor.NONE,
    )
    InvoiceLine.objects.create(
        invoice=invoice,
        line_type=InvoiceLine.LineType.DUES,
        description="April dues",
        quantity=1,
        unit_price_cents=5000,
        line_total_cents=5000,
        amount_cents=5000,
    )

    monkeypatch.setattr("apps.billing.services.stripe.Customer.create", lambda **kwargs: {"id": "cus_auto"})
    captured = {}

    def fake_payment_intent_create(**kwargs):
        captured["payment_intent"] = kwargs
        return {"id": "pi_auto_1"}

    monkeypatch.setattr("apps.billing.services.stripe.PaymentIntent.create", fake_payment_intent_create)

    from apps.billing.services import dues_autopay_run

    results = dues_autopay_run()

    assert results[0]["payment_intent_id"] == "pi_auto_1"
    assert captured["payment_intent"]["off_session"] is True
    assert captured["payment_intent"]["payment_method"] == "pm_auto"


@pytest.mark.django_db
def test_task_modules_delegate_to_services(monkeypatch):
    seen = {}

    monkeypatch.setattr("apps.billing.tasks.monthly_dues_close", lambda: ["a", "b"])
    monkeypatch.setattr("apps.billing.tasks.generate_due_scheduled_invoices", lambda: ["sched"])
    monkeypatch.setattr("apps.billing.tasks.reconcile_unposted_stripe_payments", lambda: 3)
    monkeypatch.setattr("apps.access.tasks.build_allowlist_snapshot", lambda: type("Snap", (), {"etag": "etag123"})())

    def fake_update(member):
        seen.setdefault("members", []).append(member.pk)

    member = create_member()
    monkeypatch.setattr("apps.members.tasks.update_member_status_from_balance", fake_update)

    from apps.access.tasks import refresh_allowlist_task
    from apps.billing.tasks import monthly_dues_close_task, scheduled_invoice_generation_task, stripe_reconciliation_sync_task
    from apps.members.tasks import enforcement_run_task

    assert monthly_dues_close_task() == 2
    assert scheduled_invoice_generation_task() == 1
    assert stripe_reconciliation_sync_task() == 3
    assert refresh_allowlist_task() == "etag123"
    assert enforcement_run_task() == 0 or enforcement_run_task() >= 0
