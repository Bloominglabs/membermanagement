from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.billing.services import reconcile_unposted_stripe_payments


class Command(BaseCommand):
    help = "Report how many Stripe payments still need payout and fee reconciliation."

    def handle(self, *args, **options):
        pending = reconcile_unposted_stripe_payments()
        self.stdout.write(self.style.SUCCESS(f"{pending} succeeded Stripe payments still need reconciliation."))
