from __future__ import annotations

import io

import pytest

from apps.billing.models import Invoice
from apps.expenses.models import ExpenseCategorizationRule, ExpenseCategory, ImportedBankTransaction
from apps.members.models import Client, Member


def create_member(name: str, email: str, *, door_access_enabled: bool = False) -> Member:
    client = Client.objects.create(
        client_type=Client.ClientType.PERSON,
        display_name_text=name,
        email=email,
    )
    return Member.objects.create(
        client=client,
        status=Member.Status.ACTIVE,
        membership_class=Member.MembershipClass.FULL,
        voting_eligible=True,
        door_access_enabled=door_access_enabled,
        joined_at="2026-01-01",
    )


@pytest.mark.django_db
def test_donations_manual_create_and_list_api(staff_client):
    create_response = staff_client.post(
        "/api/donations/manual",
        data={
            "external_charge_id": "manual-donation-001",
            "donor_name": "Shop Supporter",
            "donor_email": "supporter@example.org",
            "amount_cents": 3000,
            "net_amount_cents": 3000,
            "currency": "usd",
            "frequency": "one_time",
            "donation_date": "2026-04-07T00:00:00Z",
            "payment_method": "cash",
            "designation": "Metal Shop"
        },
        content_type="application/json",
    )
    list_response = staff_client.get("/api/donations")

    assert create_response.status_code == 201
    assert list_response.status_code == 200
    assert list_response.json()[0]["designation"] == "Metal Shop"


@pytest.mark.django_db
def test_expense_csv_import_categorize_and_import_batch_listing(staff_client):
    source_response = staff_client.post(
        "/api/expenses/import/csv",
        data={
            "source_name": "Checking CSV",
            "parser_key": "generic_csv",
            "csv_content": "posted_on,description,amount_cents,direction,currency\n2026-04-08,Internet Provider,800,DEBIT,usd\n",
        },
        content_type="application/json",
    )

    assert source_response.status_code == 201
    payload = source_response.json()
    imported_transaction_id = payload["transactions"][0]["id"]

    categorize_response = staff_client.post(
        f"/api/expenses/{imported_transaction_id}/categorize",
        data={"category_code": "INTERNET", "category_name": "Internet"},
        content_type="application/json",
    )
    batches_response = staff_client.get("/api/expenses/import-batches")

    assert categorize_response.status_code == 200
    assert batches_response.status_code == 200
    assert batches_response.json()[0]["transaction_count"] == 1


@pytest.mark.django_db
def test_expense_csv_import_marks_duplicate_rows_on_repeat_import(staff_client):
    payload = {
        "source_name": "Checking CSV",
        "parser_key": "generic_csv",
        "csv_content": "posted_on,description,amount_cents,direction,currency\n2026-04-08,Internet Provider,800,DEBIT,usd\n",
    }

    first_response = staff_client.post("/api/expenses/import/csv", data=payload, content_type="application/json")
    second_response = staff_client.post("/api/expenses/import/csv", data=payload, content_type="application/json")

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_response.json()["transactions"][0]["is_duplicate"] is False
    assert second_response.json()["transactions"][0]["is_duplicate"] is True


@pytest.mark.django_db
def test_expense_categorize_reassigns_existing_expense_category(staff_client):
    import_response = staff_client.post(
        "/api/expenses/import/csv",
        data={
            "source_name": "Checking CSV",
            "parser_key": "generic_csv",
            "csv_content": "posted_on,description,amount_cents,direction,currency\n2026-04-08,Mixed Vendor,800,DEBIT,usd\n",
        },
        content_type="application/json",
    )
    transaction_id = import_response.json()["transactions"][0]["id"]

    first_categorize = staff_client.post(
        f"/api/expenses/{transaction_id}/categorize",
        data={"category_code": "INTERNET", "category_name": "Internet"},
        content_type="application/json",
    )
    second_categorize = staff_client.post(
        f"/api/expenses/{transaction_id}/categorize",
        data={"category_code": "UTIL", "category_name": "Utilities"},
        content_type="application/json",
    )

    assert first_categorize.status_code == 200
    assert second_categorize.status_code == 200
    assert second_categorize.json()["category"] == "UTIL"


@pytest.mark.django_db
def test_expense_csv_import_auto_categorizes_from_rules(staff_client):
    category = ExpenseCategory.objects.create(code="INTERNET", name="Internet")
    ExpenseCategorizationRule.objects.create(
        priority=1,
        match_type=ExpenseCategorizationRule.MatchType.CONTAINS,
        pattern="internet",
        expense_category=category,
    )
    response = staff_client.post(
        "/api/expenses/import/csv",
        data={
            "source_name": "Checking CSV",
            "parser_key": "generic_csv",
            "csv_content": "posted_on,description,amount_cents,direction,currency\n2026-04-08,Internet Provider,800,DEBIT,usd\n",
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    transaction = ImportedBankTransaction.objects.get(pk=response.json()["transactions"][0]["id"])
    assert transaction.expense is not None
    assert transaction.expense.category == category
    assert transaction.is_reconciled is False


@pytest.mark.django_db
def test_member_balances_and_ar_aging_reports(staff_client):
    member = create_member("Aging Member", "aging@example.org")
    Invoice.objects.create(
        client=member.client,
        member=member,
        invoice_type=Invoice.InvoiceType.MEMBER_DUES,
        invoice_number="INV-AGING-001",
        issue_date="2026-01-01",
        due_date="2026-01-15",
        service_period_start="2026-01-01",
        service_period_end="2026-01-31",
        status=Invoice.Status.ISSUED,
        total_cents=5000,
        external_processor=Invoice.ExternalProcessor.NONE,
    )

    balances_response = staff_client.get("/api/reports/member-balances")
    aging_response = staff_client.get("/api/reports/ar-aging")

    assert balances_response.status_code == 200
    assert aging_response.status_code == 200
    assert balances_response.json()[0]["receivable_cents"] == 5000
    assert aging_response.json()["total_receivables_cents"] == 5000


@pytest.mark.django_db
def test_allowlist_endpoint_returns_door_access_flags(access_agent_client):
    create_member("Door Enabled", "door1@example.org", door_access_enabled=True)
    create_member("Door Disabled", "door2@example.org", door_access_enabled=False)

    response = access_agent_client.get("/api/access/allowlist/")

    assert response.status_code == 200
    entries = response.json()["payload"]["members"]
    assert any(entry["door_access_enabled"] is True for entry in entries)
