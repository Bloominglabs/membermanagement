from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.billing.services import stripe_reconciliation_sync


class Command(BaseCommand):
    help = "Backfill Stripe balance transaction identifiers for succeeded Stripe payments."

    def handle(self, *args, **options):
        result = stripe_reconciliation_sync()
        if not result.configured:
            self.stdout.write(
                self.style.WARNING(
                    f"Stripe is not configured; {result.pending_count} succeeded Stripe payments are still pending reconciliation."
                )
            )
            return
        self.stdout.write(
            self.style.SUCCESS(
                "Stripe reconciliation sync scanned "
                f"{result.scanned_count} payments, reconciled {result.reconciled_count}, "
                f"left {result.pending_count} pending, and hit {result.error_count} lookup errors."
            )
        )
