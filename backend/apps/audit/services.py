from __future__ import annotations

from apps.audit.models import AuditLog


def log_audit_event(
    *,
    actor: str = "system",
    verb: str = "",
    object_type: str = "",
    object_id: str = "",
    changes: dict | None = None,
    message: str = "",
    actor_type: str = "system",
    actor_id: str = "",
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    before_json: dict | None = None,
    after_json: dict | None = None,
    reason: str = "",
) -> AuditLog:
    return AuditLog.objects.create(
        actor=actor,
        verb=verb or action or "",
        object_type=object_type or entity_type or "",
        object_id=object_id or entity_id or "",
        changes=changes or {},
        message=message,
        actor_type=actor_type,
        actor_id=actor_id,
        entity_type=entity_type or object_type or "",
        entity_id=entity_id or object_id or "",
        action=action or verb,
        before_json=before_json or {},
        after_json=after_json or {},
        reason=reason,
    )
