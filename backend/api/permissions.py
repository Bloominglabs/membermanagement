from __future__ import annotations

from django.conf import settings
from rest_framework.permissions import BasePermission


class UserOrAccessAgentKeyPermission(BasePermission):
    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            return True
        configured_key = getattr(settings, "ACCESS_AGENT_API_KEY", "")
        if not configured_key:
            return False
        return request.headers.get("X-Access-Agent-Key", "") == configured_key
