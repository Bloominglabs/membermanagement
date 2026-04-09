from __future__ import annotations

from celery import shared_task

from apps.access.services import build_allowlist_snapshot


@shared_task
def refresh_allowlist_task() -> str:
    return build_allowlist_snapshot().etag
