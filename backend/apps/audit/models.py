from __future__ import annotations

from django.db import models
from django.utils import timezone


class AuditLog(models.Model):
    occurred_at = models.DateTimeField(default=timezone.now)
    actor_type = models.CharField(max_length=100, blank=True)
    actor_id = models.CharField(max_length=100, blank=True)
    entity_type = models.CharField(max_length=100, blank=True)
    entity_id = models.CharField(max_length=100, blank=True)
    action = models.CharField(max_length=100, blank=True)
    before_json = models.JSONField(default=dict, blank=True)
    after_json = models.JSONField(default=dict, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    actor = models.CharField(max_length=255)
    verb = models.CharField(max_length=100)
    object_type = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100)
    message = models.CharField(max_length=255, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]
