from __future__ import annotations

import pytest

from apps.billing.models import Invoice, InvoiceSchedule
from apps.expenses.models import ExpenseCategorizationRule, ExpenseCategory
from apps.members.models import Client, Member


def create_member() -> Member:
    client = Client.objects.create(
        client_type=Client.ClientType.PERSON,
        display_name_text="Schedule Member",
        email=f"schedule-{Client.objects.count() + 1}@example.org",
    )
    return Member.objects.create(
        client=client,
        status=Member.Status.ACTIVE,
        membership_class=Member.MembershipClass.FULL,
        voting_eligible=True,
        joined_at="2026-01-01",
    )


@pytest.mark.django_db
def test_invoice_schedule_api_create_list_and_patch(staff_client):
    member = create_member()

    create_response = staff_client.post(
        "/api/invoice-schedules/",
        data={
            "client": member.client.pk,
            "member": member.pk,
            "invoice_type": Invoice.InvoiceType.RECURRING_AD_HOC,
            "description": "Quarterly tool fee",
            "frequency": InvoiceSchedule.Frequency.QUARTERLY,
            "generation_day": 10,
            "due_offset_days": 20,
            "amount_cents": 12000,
            "active": True,
        },
        content_type="application/json",
    )

    assert create_response.status_code == 201
    schedule_id = create_response.json()["id"]

    list_response = staff_client.get("/api/invoice-schedules/")
    patch_response = staff_client.patch(
        f"/api/invoice-schedules/{schedule_id}/",
        data={"active": False, "due_day": 25},
        content_type="application/json",
    )

    assert list_response.status_code == 200
    assert list_response.json()[0]["description"] == "Quarterly tool fee"
    assert patch_response.status_code == 200
    assert patch_response.json()["active"] is False
    assert patch_response.json()["due_day"] == 25


@pytest.mark.django_db
def test_expense_categorization_rule_api_create_list_and_patch(staff_client):
    category = ExpenseCategory.objects.create(code="TOOLS", name="Tools")

    create_response = staff_client.post(
        "/api/expense-categorization-rules/",
        data={
            "priority": 10,
            "match_type": ExpenseCategorizationRule.MatchType.CONTAINS,
            "pattern": "harbor freight",
            "expense_category": category.pk,
            "vendor_name": "Harbor Freight",
            "active": True,
        },
        content_type="application/json",
    )

    assert create_response.status_code == 201
    rule_id = create_response.json()["id"]

    list_response = staff_client.get("/api/expense-categorization-rules/")
    patch_response = staff_client.patch(
        f"/api/expense-categorization-rules/{rule_id}/",
        data={"priority": 5, "active": False},
        content_type="application/json",
    )

    assert list_response.status_code == 200
    assert list_response.json()[0]["pattern"] == "harbor freight"
    assert patch_response.status_code == 200
    assert patch_response.json()["priority"] == 5
    assert patch_response.json()["active"] is False
