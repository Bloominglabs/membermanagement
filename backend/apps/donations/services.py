from __future__ import annotations

from datetime import datetime

from django.db import transaction
from django.utils import timezone

from apps.donations.models import Donation


@transaction.atomic
def process_everyorg_webhook(payload: dict) -> Donation:
    donation_date = payload.get("donationDate")
    if donation_date:
        parsed_donation_date = datetime.fromisoformat(donation_date.replace("Z", "+00:00"))
    else:
        parsed_donation_date = timezone.now()

    donor = payload.get("donor") or {}
    donation, _ = Donation.objects.update_or_create(
        external_charge_id=payload["chargeId"],
        defaults={
            "donor_name": donor.get("name", ""),
            "donor_email": donor.get("email", ""),
            "amount_cents": int(payload.get("amount", 0)),
            "net_amount_cents": int(payload.get("netAmount", 0)) if payload.get("netAmount") is not None else None,
            "currency": payload.get("currency", "usd"),
            "frequency": payload.get("frequency", ""),
            "donation_date": parsed_donation_date,
            "payment_method": payload.get("paymentMethod", ""),
            "designation": payload.get("designation", ""),
            "partner_metadata": payload.get("partner_metadata") or {},
            "raw_payload": payload,
        },
    )
    return donation
