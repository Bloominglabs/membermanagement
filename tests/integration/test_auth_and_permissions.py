from __future__ import annotations

import pytest
from django.test import Client as DjangoClient

from apps.members.models import Client, Member


def create_member() -> Member:
    client = Client.objects.create(
        client_type=Client.ClientType.PERSON,
        display_name_text="Protected Member",
        email="protected@example.org",
    )
    return Member.objects.create(
        client=client,
        status=Member.Status.ACTIVE,
        membership_class=Member.MembershipClass.FULL,
        voting_eligible=True,
        joined_at="2026-01-01",
    )


@pytest.mark.django_db
def test_management_api_requires_authenticated_user():
    response = DjangoClient().get("/api/members/")

    assert response.status_code in {401, 403}


@pytest.mark.django_db
def test_management_api_allows_authenticated_staff(staff_client):
    response = staff_client.get("/api/members/")

    assert response.status_code == 200


@pytest.mark.django_db
def test_access_api_requires_access_agent_key_or_authenticated_user(settings):
    settings.ACCESS_AGENT_API_KEY = "access-agent-test-key"
    member = create_member()

    anonymous_response = DjangoClient().get("/api/access/allowlist/")
    key_response = DjangoClient().get(
        "/api/access/allowlist/",
        HTTP_X_ACCESS_AGENT_KEY="access-agent-test-key",
    )
    entitlement_response = DjangoClient().get(
        f"/api/access/members/{member.pk}/entitlement",
        HTTP_X_ACCESS_AGENT_KEY="access-agent-test-key",
    )

    assert anonymous_response.status_code in {401, 403}
    assert key_response.status_code == 200
    assert entitlement_response.status_code == 200


@pytest.mark.django_db
def test_healthz_is_public():
    response = DjangoClient().get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
