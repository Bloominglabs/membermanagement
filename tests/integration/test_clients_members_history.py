from __future__ import annotations

import pytest
from django.test import Client as DjangoClient

from apps.audit.models import AuditLog
from apps.members.models import Client, ClientAlias, Member, MembershipTerm


@pytest.mark.django_db
def test_client_api_create_and_update_records_aliases_and_audit_log():
    client = DjangoClient()

    create_response = client.post(
        "/api/clients/",
        data={
            "client_type": "PERSON",
            "display_name": "Jane Maker",
            "legal_name": "Jane Q. Maker",
            "primary_email": "jane@example.org",
            "primary_phone": "555-0101",
            "address_line1": "123 Main",
            "city": "Bloomington",
            "state": "IN",
            "postal_code": "47401",
            "country": "US",
            "notes": "Initial record",
            "is_active": True,
        },
        content_type="application/json",
    )

    assert create_response.status_code == 201
    client_id = create_response.json()["id"]

    patch_response = client.patch(
        f"/api/clients/{client_id}/",
        data={
            "display_name": "Jane M. Maker",
            "primary_email": "jane.maker@example.org",
        },
        content_type="application/json",
    )

    assert patch_response.status_code == 200
    stored_client = Client.objects.get(pk=client_id)
    assert stored_client.primary_email == "jane.maker@example.org"
    assert ClientAlias.objects.filter(client=stored_client, alias_type=ClientAlias.AliasType.EMAIL, value="jane@example.org").exists()
    assert ClientAlias.objects.filter(client=stored_client, alias_type=ClientAlias.AliasType.NAME, value="Jane Maker").exists()
    assert AuditLog.objects.filter(entity_type="Client", entity_id=str(client_id), action="client.updated").exists()


@pytest.mark.django_db
def test_member_history_endpoint_returns_terms_and_audit_entries():
    client = DjangoClient()
    create_response = client.post(
        "/api/members/",
        data={
            "client": {
                "client_type": "PERSON",
                "display_name": "Pat Builder",
                "primary_email": "pat@example.org",
                "primary_phone": "",
                "address_line1": "",
                "address_line2": "",
                "city": "",
                "state": "",
                "postal_code": "",
                "country": "US",
                "notes": "",
                "is_active": True,
            },
            "membership_class": "FULL",
            "membership_status": "ACTIVE",
            "voting_eligible": True,
            "door_access_enabled": True,
            "joined_on": "2026-01-01",
            "autopay_enabled": False,
            "notes": "",
            "reason": "Initial join"
        },
        content_type="application/json",
    )

    assert create_response.status_code == 201
    member_id = create_response.json()["id"]

    patch_response = client.patch(
        f"/api/members/{member_id}/",
        data={
            "membership_class": "HARDSHIP",
            "voting_eligible": False,
            "door_access_enabled": False,
            "reason": "Hardship adjustment",
        },
        content_type="application/json",
    )

    assert patch_response.status_code == 200
    member = Member.objects.get(pk=member_id)
    assert member.membership_class == Member.MembershipClass.HARDSHIP
    assert MembershipTerm.objects.filter(member=member).count() == 2

    history_response = client.get(f"/api/members/{member_id}/history")

    assert history_response.status_code == 200
    payload = history_response.json()
    assert len(payload["membership_terms"]) == 2
    assert any(entry["action"] == "member.updated" for entry in payload["audit_log"])


@pytest.mark.django_db
def test_access_entitlement_endpoint_reflects_member_flag():
    client_record = Client.objects.create(
        client_type=Client.ClientType.PERSON,
        display_name_text="Alex Access",
        primary_email="alex@example.org",
    )
    member = Member.objects.create(
        client=client_record,
        status=Member.Status.ACTIVE,
        membership_class=Member.MembershipClass.FULL,
        voting_eligible=True,
        door_access_enabled=False,
        joined_at="2026-01-01",
    )

    response = DjangoClient().get(f"/api/access/members/{member.pk}/entitlement")

    assert response.status_code == 200
    payload = response.json()
    assert payload["member_id"] == member.pk
    assert payload["door_access_enabled"] is False
