from __future__ import annotations

from django.db import models


class Donation(models.Model):
    external_charge_id = models.CharField(max_length=255, unique=True)
    donor_name = models.CharField(max_length=255, blank=True)
    donor_email = models.EmailField(blank=True)
    amount_cents = models.PositiveIntegerField()
    net_amount_cents = models.PositiveIntegerField(blank=True, null=True)
    currency = models.CharField(max_length=10, default="usd")
    frequency = models.CharField(max_length=50, blank=True)
    donation_date = models.DateTimeField()
    payment_method = models.CharField(max_length=50, blank=True)
    designation = models.CharField(max_length=255, blank=True)
    partner_metadata = models.JSONField(default=dict, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-donation_date", "-id"]
