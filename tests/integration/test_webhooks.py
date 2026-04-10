from __future__ import annotations

import json
import time

import pytest
import stripe
from django.test import Client as DjangoClient

from apps.billing.models import Payment, ProcessorChoices, WebhookEvent
from apps.donations.models import Donation
from apps.members.models import Client, Member


def stripe_signature_header(payload: bytes, secret: str) -> str:
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
    signature = stripe.WebhookSignature._compute_signature(signed_payload, secret)
    return f"t={timestamp},v1={signature}"


@pytest.mark.django_db
def test_stripe_webhook_rejects_invalid_signature(settings):
    settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
    payload = json.dumps({"id": "evt_invalid", "type": "payment_intent.succeeded", "data": {"object": {}}}).encode("utf-8")

    response = DjangoClient().post(
        "/webhooks/stripe/",
        data=payload,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE="t=123,v1=invalid",
    )

    assert response.status_code == 400
    event = WebhookEvent.objects.get(processor=ProcessorChoices.STRIPE)
    assert event.signature_valid is False


@pytest.mark.django_db
def test_stripe_webhook_is_idempotent(settings):
    settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
    client = Client.objects.create(first_name="Pat", last_name="Maker", email="pat@example.org")
    member = Member.objects.create(client=client, status=Member.Status.ACTIVE, joined_at="2026-01-01")
    event = {
        "id": "evt_test_payment_succeeded",
        "object": "event",
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "pi_test_123",
                "created": 1710000000,
                "amount_received": 5000,
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
    client = DjangoClient()

    first = client.post("/webhooks/stripe/", data=payload, content_type="application/json", HTTP_STRIPE_SIGNATURE=header)
    second = client.post("/webhooks/stripe/", data=payload, content_type="application/json", HTTP_STRIPE_SIGNATURE=header)

    assert first.status_code == 200
    assert second.status_code == 200
    assert Payment.objects.count() == 1
    payment = Payment.objects.get()
    assert payment.amount_cents == 5000
    assert payment.status == Payment.Status.SUCCEEDED
    assert WebhookEvent.objects.count() == 1


@pytest.mark.django_db
def test_everyorg_webhook_rejects_invalid_token_when_configured(settings):
    settings.EVERYORG_WEBHOOK_TOKEN = "every-token"
    payload = {"chargeId": "every-bad-token", "amount": 1000}

    response = DjangoClient().post(
        "/webhooks/everyorg/nonprofit-donation/",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == 403
    assert Donation.objects.count() == 0


@pytest.mark.django_db
def test_everyorg_webhook_stores_designation_and_allows_anonymous_donor():
    payload = {
        "chargeId": "every-123",
        "amount": 1500,
        "netAmount": 1300,
        "currency": "usd",
        "frequency": "one_time",
        "donationDate": "2026-04-04T00:00:00Z",
        "paymentMethod": "card",
        "designation": "Wood Shop",
        "donor": {"name": "Anonymous"},
    }

    response = DjangoClient().post(
        "/webhooks/everyorg/nonprofit-donation/",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == 200
    donation = Donation.objects.get(external_charge_id="every-123")
    assert donation.designation == "Wood Shop"
    assert donation.donor_email == ""


@pytest.mark.django_db
def test_everyorg_webhook_accepts_configured_token(settings):
    settings.EVERYORG_WEBHOOK_TOKEN = "every-token"
    payload = {
        "chargeId": "every-124",
        "amount": 1500,
        "netAmount": 1300,
        "currency": "usd",
        "frequency": "one_time",
        "donationDate": "2026-04-04T00:00:00Z",
        "paymentMethod": "card",
        "designation": "Wood Shop",
        "donor": {"name": "Anonymous"},
    }

    response = DjangoClient().post(
        "/webhooks/everyorg/nonprofit-donation/?token=every-token",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == 200
    donation = Donation.objects.get(external_charge_id="every-124")
    assert donation.designation == "Wood Shop"
    assert donation.donor_email == ""
