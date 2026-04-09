from __future__ import annotations

import hashlib
import hmac
import json

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.access.models import AccessAllowlistSnapshot, AccessEvent, RFIDCredential
from apps.common.utils import json_ready
from apps.members.models import Member


def _sign_payload(payload: dict) -> tuple[str, str]:
    raw_payload = json.dumps(json_ready(payload), sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hmac.new(settings.ACCESS_ALLOWLIST_SECRET.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()
    etag = hashlib.sha256(raw_payload).hexdigest()
    return etag, digest


@transaction.atomic
def build_allowlist_snapshot() -> AccessAllowlistSnapshot:
    members = Member.objects.filter(status__in=[Member.Status.ACTIVE, Member.Status.PAST_DUE]).select_related("client").order_by("id")
    payload = {
        "generated_at": timezone.now(),
        "members": [
            {
                "member_id": member.id,
                "member_number": member.member_number,
                "credential_ids": list(member.rfid_credentials.filter(is_active=True).values_list("uid", flat=True)),
                "door_access_enabled": member.door_access_enabled,
                "updated_at": member.updated_at,
            }
            for member in members
        ],
    }
    etag, signature = _sign_payload(payload)
    snapshot = AccessAllowlistSnapshot.objects.create(etag=etag, payload_json=json_ready(payload), signature=signature)
    return snapshot


def record_access_event(*, credential_uid: str, result: str, member: Member | None = None, details: dict | None = None) -> AccessEvent:
    return AccessEvent.objects.create(
        member=member,
        credential_uid=credential_uid,
        result=result,
        details=details or {},
    )
