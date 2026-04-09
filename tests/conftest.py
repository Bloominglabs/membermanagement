from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.test import Client as DjangoClient

ROOT_DIR = Path(__file__).resolve().parents[1]
for candidate in (ROOT_DIR / ".pkg", ROOT_DIR / "backend", ROOT_DIR):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


@pytest.fixture
def staff_user(db):
    user_model = get_user_model()
    return user_model.objects.create_user(
        username="treasurer",
        email="treasurer@example.org",
        password="test-password",
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def staff_client(staff_user):
    client = DjangoClient()
    client.force_login(staff_user)
    return client


@pytest.fixture
def access_agent_client(settings):
    settings.ACCESS_AGENT_API_KEY = "access-agent-test-key"
    client = DjangoClient()
    client.defaults["HTTP_X_ACCESS_AGENT_KEY"] = "access-agent-test-key"
    return client
