from __future__ import annotations

import pytest

from apps.billing.models import Invoice, InvoiceLine, Payment
from apps.billing.services import allocate_payment_fifo
from apps.donations.models import Donation
from apps.expenses.models import Expense, ExpenseCategory
from apps.members.models import Client, Member


def create_member(name: str, email: str) -> Member:
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
        joined_at="2026-01-01",
    )


def create_invoice(member: Member, number: str, total_cents: int, status: str = Invoice.Status.DRAFT) -> Invoice:
    invoice = Invoice.objects.create(
        client=member.client,
        member=member,
        invoice_type=Invoice.InvoiceType.MEMBER_DUES,
        invoice_number=number,
        issue_date="2026-04-01",
        due_date="2026-04-15",
        service_period_start="2026-04-01",
        service_period_end="2026-04-30",
        status=status,
        total_cents=total_cents,
        external_processor=Invoice.ExternalProcessor.NONE,
    )
    InvoiceLine.objects.create(
        invoice=invoice,
        line_type=InvoiceLine.LineType.DUES,
        description="April dues",
        quantity=1,
        unit_price_cents=total_cents,
        line_total_cents=total_cents,
    )
    return invoice


@pytest.mark.django_db
def test_invoice_issue_and_void_endpoints(staff_client):
    member = create_member("Invoice Person", "invoice@example.org")
    invoice = create_invoice(member, "INV-API-001", 5000, status=Invoice.Status.DRAFT)

    issue_response = staff_client.post(f"/api/invoices/{invoice.pk}/issue", content_type="application/json")
    void_response = staff_client.post(f"/api/invoices/{invoice.pk}/void", content_type="application/json")

    assert issue_response.status_code == 200
    assert void_response.status_code == 200
    invoice.refresh_from_db()
    assert invoice.status == Invoice.Status.VOID


@pytest.mark.django_db
def test_financial_report_endpoint_returns_summary_dues_donations_expenses_and_snapshot(staff_client):
    paid_member = create_member("Paid Member", "paid@example.org")
    unpaid_member = create_member("Unpaid Member", "unpaid@example.org")
    paid_invoice = create_invoice(paid_member, "INV-RPT-001", 5000, status=Invoice.Status.ISSUED)
    unpaid_invoice = create_invoice(unpaid_member, "INV-RPT-002", 5000, status=Invoice.Status.ISSUED)
    payment = Payment.objects.create(
        client=paid_member.client,
        member=paid_member,
        received_at="2026-04-04T12:00:00Z",
        amount_cents=6500,
        source_type=Payment.SourceType.PREPAYMENT_TOPUP,
        payment_method=Payment.PaymentMethod.CASH,
        status=Payment.Status.SUCCEEDED,
    )
    allocate_payment_fifo(payment)
    Donation.objects.create(
        external_charge_id="every-rpt-001",
        donor_name="Anonymous",
        donor_email="",
        amount_cents=2500,
        net_amount_cents=2300,
        donation_date="2026-04-05T00:00:00Z",
        payment_method="card",
        designation="Laser Cutter",
    )
    category = ExpenseCategory.objects.create(code="INTERNET", name="Internet")
    Expense.objects.create(
        description="Internet",
        booked_on="2026-04-06",
        amount_cents=800,
        category=category,
        review_status=Expense.ReviewStatus.RECONCILED,
    )

    response = staff_client.get("/api/reports/financial?from=2026-04-01&to=2026-04-30")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["earned_dues_cents"] == 5000
    assert payload["summary"]["cash_in_cents"] == 9000
    assert payload["summary"]["donations_received_cents"] == 2500
    assert payload["dues"]["unpaid_dues_outstanding_cents"] == 5000
    assert payload["donations"]["by_designation"]["Laser Cutter"] == 2500
    assert payload["expenses"]["categorized_expenses_cents"] == 800
    assert payload["expenses"]["by_category_cents"]["INTERNET"] == 800
    assert payload["balance_snapshot"]["member_prepayment_liability_cents"] == 1500
    assert payload["balance_snapshot"]["accounts_receivable_cents"] == 5000
