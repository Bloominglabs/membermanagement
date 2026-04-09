from __future__ import annotations

from celery import shared_task

from apps.members.models import Member
from apps.members.services import update_member_status_from_balance


@shared_task
def enforcement_run_task() -> int:
    updated = 0
    for member in Member.objects.select_related("client").all():
        previous = member.status
        update_member_status_from_balance(member)
        member.refresh_from_db(fields=["status"])
        if member.status != previous:
            updated += 1
    return updated
