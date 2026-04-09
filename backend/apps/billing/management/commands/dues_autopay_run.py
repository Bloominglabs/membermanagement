from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.billing.services import dues_autopay_run


class Command(BaseCommand):
    help = "Attempt Stripe off-session charges for members enrolled in autopay."

    def handle(self, *args, **options):
        results = dues_autopay_run()
        self.stdout.write(self.style.SUCCESS(f"Created {len(results)} autopay Stripe PaymentIntents."))
