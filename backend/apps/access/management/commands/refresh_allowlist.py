from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.access.services import build_allowlist_snapshot


class Command(BaseCommand):
    help = "Build and persist a new signed RFID allowlist snapshot."

    def handle(self, *args, **options):
        snapshot = build_allowlist_snapshot()
        self.stdout.write(self.style.SUCCESS(f"Created allowlist snapshot {snapshot.etag}."))
