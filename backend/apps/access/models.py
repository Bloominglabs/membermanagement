from __future__ import annotations

from django.db import models


class RFIDCredential(models.Model):
    member = models.ForeignKey("members.Member", on_delete=models.CASCADE, related_name="rfid_credentials")
    uid = models.CharField(max_length=255, unique=True)
    label = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uid"]


class AccessAllowlistSnapshot(models.Model):
    etag = models.CharField(max_length=64, unique=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    payload_json = models.JSONField(default=dict)
    signature = models.CharField(max_length=128)

    class Meta:
        ordering = ["-generated_at", "-id"]


class AccessEvent(models.Model):
    occurred_at = models.DateTimeField(auto_now_add=True)
    member = models.ForeignKey(
        "members.Member",
        on_delete=models.SET_NULL,
        related_name="access_events",
        blank=True,
        null=True,
    )
    credential_uid = models.CharField(max_length=255)
    result = models.CharField(max_length=50)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]
