from __future__ import annotations

from datetime import date, timedelta

import pytest

from apps.billing.models import Invoice, InvoiceLine, Payment
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


def create_invoice(member: Member, *, number: str, due_date: date, total_cents: int = 1000) -> Invoice:
    invoice = Invoice.objects.create(
        client=member.client,
        member=member,
        invoice_type=Invoice.InvoiceType.MEMBER_DUES,
        invoice_number=number,
        issue_date=due_date.replace(day=1),
        due_date=due_date,
        service_period_start=due_date.replace(day=1),
        service_period_end=due_date.replace(day=min(28, due_date.day)),
        status=Invoice.Status.ISSUED,
        total_cents=total_cents,
        external_processor=Invoice.ExternalProcessor.NONE,
    )
    InvoiceLine.objects.create(
        invoice=invoice,
        line_type=InvoiceLine.LineType.DUES,
        description=number,
        quantity=1,
        unit_price_cents=total_cents,
        line_total_cents=total_cents,
        amount_cents=total_cents,
    )
    return invoice


@pytest.mark.django_db
def test_member_manual_payment_balance_endpoint_and_csv_exports(staff_client):
    member = create_member("CSV Member", "csv-member@example.org")
    create_invoice(member, number="INV-MEMBER-ACTION-001", due_date=date(2026, 4, 15), total_cents=5000)

    manual_payment = staff_client.post(
        f"/api/members/{member.pk}/manual-payment/",
        data={
            "amount_cents": 5000,
            "payment_method": "CASH",
            "source_type": "DUES_PAYMENT",
            "note": "cash box",
        },
        content_type="application/json",
    )
    balance_response = staff_client.get(f"/api/members/{member.pk}/balance/")
    financial_csv = staff_client.get("/api/exports/financial.csv?from=2026-04-01&to=2026-04-30")
    balances_csv = staff_client.get("/api/exports/member-balances.csv")

    assert manual_payment.status_code == 201
    assert balance_response.status_code == 200
    assert balance_response.json()["receivable_cents"] == 0
    assert financial_csv.status_code == 200
    assert "earned_dues_cents" in financial_csv.content.decode("utf-8")
    assert balances_csv.status_code == 200
    assert "member_name" in balances_csv.content.decode("utf-8")


@pytest.mark.django_db
def test_ar_aging_report_buckets_include_current_and_overdue_ranges(staff_client):
    member = create_member("Aging Buckets", "aging-buckets@example.org")
    today = date.today()
    create_invoice(member, number="INV-CURRENT", due_date=today + timedelta(days=1), total_cents=1000)
    one_thirty = create_invoice(member, number="INV-1-30", due_date=today - timedelta(days=10), total_cents=1100)
    create_invoice(member, number="INV-31-60", due_date=today - timedelta(days=40), total_cents=1200)
    create_invoice(member, number="INV-61-90", due_date=today - timedelta(days=70), total_cents=1300)
    create_invoice(member, number="INV-OVER-90", due_date=today - timedelta(days=100), total_cents=1400)
    paid_invoice = create_invoice(member, number="INV-PAID", due_date=today - timedelta(days=5), total_cents=1500)
    payment = Payment.objects.create(
        client=member.client,
        member=member,
        received_at="2026-04-10T00:00:00Z",
        amount_cents=1500,
        payment_method=Payment.PaymentMethod.CASH,
        source_type=Payment.SourceType.DUES_PAYMENT,
        status=Payment.Status.SUCCEEDED,
    )
    paid_invoice.allocations.create(payment=payment, allocated_cents=1500)
    one_thirty.allocations.create(payment=payment, allocated_cents=200)

    response = staff_client.get("/api/reports/ar-aging")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_receivables_cents"] == 5800
    assert payload["buckets"]["current"] == 1000
    assert payload["buckets"]["1_30"] == 900
    assert payload["buckets"]["31_60"] == 1200
    assert payload["buckets"]["61_90"] == 1300
    assert payload["buckets"]["over_90"] == 1400
