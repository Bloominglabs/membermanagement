from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.billing.services import monthly_dues_close


class Command(BaseCommand):
    help = "Create the monthly dues charge for each active/past-due member and auto-apply existing credits."

    def handle(self, *args, **options):
        invoices = monthly_dues_close()
        self.stdout.write(self.style.SUCCESS(f"Generated or confirmed {len(invoices)} dues invoices."))
