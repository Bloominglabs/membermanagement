from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.members.models import Member
from apps.members.services import update_member_status_from_balance


class Command(BaseCommand):
    help = "Recompute balances and apply membership status enforcement rules."

    def handle(self, *args, **options):
        updated = 0
        for member in Member.objects.select_related("client").all():
            previous = member.status
            update_member_status_from_balance(member)
            member.refresh_from_db(fields=["status"])
            if member.status != previous:
                updated += 1
        self.stdout.write(self.style.SUCCESS(f"Updated {updated} member statuses."))
