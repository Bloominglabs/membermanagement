from __future__ import annotations

import json
import time

import pytest
import stripe

from apps.billing.models import Invoice, InvoiceLine, Payment
from apps.members.models import Client, Member


def stripe_signature_header(payload: bytes, secret: str) -> str:
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
    signature = stripe.WebhookSignature._compute_signature(signed_payload, secret)
    return f"t={timestamp},v1={signature}"


def create_member() -> Member:
    client = Client.objects.create(
        client_type=Client.ClientType.PERSON,
        display_name_text=f"API Branch {Client.objects.count() + 1}",
        email=f"api-branch-{Client.objects.count() + 1}@example.org",
    )
    return Member.objects.create(
        client=client,
        status=Member.Status.ACTIVE,
        membership_class=Member.MembershipClass.FULL,
        voting_eligible=True,
        joined_at="2026-01-01",
    )


@pytest.mark.django_db
def test_manual_payment_and_allocate_endpoints(staff_client):
    member = create_member()
    invoice = Invoice.objects.create(
        client=member.client,
        member=member,
        invoice_type=Invoice.InvoiceType.MEMBER_DUES,
        invoice_number="INV-API-ALLOC-001",
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
    create_response = staff_client.post(
        "/api/payments/manual",
        data={
            "client": member.client.pk,
            "member": member.pk,
            "received_at": "2026-04-10T00:00:00Z",
            "amount_cents": 5000,
            "currency": "usd",
            "payment_method": "CASH",
            "source_type": "DUES_PAYMENT",
            "status": "SUCCEEDED",
            "notes": "desk cash",
            "metadata": {},
        },
        content_type="application/json",
    )

    assert create_response.status_code == 201
    payment_id = create_response.json()["id"]
    allocate_response = staff_client.post(
        f"/api/payments/{payment_id}/allocate",
        data={"invoice_ids": [invoice.pk]},
        content_type="application/json",
    )

    assert allocate_response.status_code == 200
    invoice.refresh_from_db()
    assert invoice.status == Invoice.Status.PAID


@pytest.mark.django_db
def test_invoice_create_uses_due_offset_and_balances_reports_route(staff_client):
    member = create_member()
    response = staff_client.post(
        "/api/invoices/",
        data={
            "client": member.client.pk,
            "member": member.pk,
            "invoice_type": "ONE_OFF",
            "invoice_number": "INV-OFFSET-001",
            "issue_date": "2026-04-03",
            "due_offset_days": 10,
            "service_period_start": "2026-04-03",
            "service_period_end": "2026-04-13",
            "status": "DRAFT",
            "currency": "usd",
            "total_cents": 0,
            "external_processor": "NONE",
            "description": "One-off fee",
            "notes": "",
            "metadata": {},
            "lines": [
                {
                    "line_type": "OTHER",
                    "description": "One-off fee",
                    "quantity": 1,
                    "unit_price_cents": 1200,
                    "line_total_cents": 1200
                }
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["due_date"] == "2026-04-13"

    balances = staff_client.get("/api/reports/member-balances")
    assert balances.status_code == 200


@pytest.mark.django_db
def test_stripe_checkout_and_setup_views_and_payment_failed_webhook(settings, monkeypatch, staff_client):
    settings.STRIPE_SECRET_KEY = "sk_test"
    settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
    member = create_member()
    captured = {}

    monkeypatch.setattr("apps.billing.services.stripe.Customer.create", lambda **kwargs: {"id": "cus_view"})
    monkeypatch.setattr(
        "apps.billing.services.stripe.checkout.Session.create",
        lambda **kwargs: {"id": "cs_view", "url": "https://stripe.test/checkout"},
    )
    monkeypatch.setattr(
        "apps.billing.services.stripe.SetupIntent.create",
        lambda **kwargs: {"id": "seti_view", "client_secret": "secret_view"},
    )

    checkout_response = staff_client.post(
        "/api/stripe/create-checkout-session",
        data={"member_id": member.pk, "mode": "top_up", "amount_cents": 1500},
        content_type="application/json",
    )
    setup_response = staff_client.post(
        "/api/stripe/create-setup-intent",
        data={"member_id": member.pk},
        content_type="application/json",
    )

    assert checkout_response.status_code == 200
    assert setup_response.status_code == 200

    event = {
        "id": "evt_payment_failed_1",
        "object": "event",
        "type": "payment_intent.payment_failed",
        "data": {
            "object": {
                "id": "pi_fail_1",
                "created": 1710000000,
                "amount": 1500,
                "currency": "usd",
                "metadata": {
                    "member_id": str(member.pk),
                    "client_id": str(member.client_id),
                    "source_type": "DUES_PAYMENT",
                },
            }
        },
    }
    payload = json.dumps(event).encode("utf-8")
    header = stripe_signature_header(payload, settings.STRIPE_WEBHOOK_SECRET)
    from django.test import Client as DjangoClient

    webhook_response = DjangoClient().post(
        "/webhooks/stripe/",
        data=payload,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=header,
    )

    assert webhook_response.status_code == 200
    assert Payment.objects.get(processor_payment_id="pi_fail_1").status == Payment.Status.FAILED


@pytest.mark.django_db
def test_allowlist_304_and_access_event_endpoint(access_agent_client):
    member = create_member()
    member.door_access_enabled = True
    member.save(update_fields=["door_access_enabled", "updated_at"])

    first = access_agent_client.get("/api/access/allowlist/")
    etag = first.json()["etag"]
    second = access_agent_client.get(f"/api/access/allowlist/?v={etag}")
    event = access_agent_client.post(
        "/api/access/events/",
        data={"credential_uid": "uid-123", "result": "granted", "member_id": member.pk, "details": {"door": "front"}},
        content_type="application/json",
    )

    assert first.status_code == 200
    assert second.status_code == 304
    assert event.status_code == 201
