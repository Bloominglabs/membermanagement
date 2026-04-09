from __future__ import annotations

from datetime import date

import pytest

from apps.billing.models import Invoice, InvoiceLine, Payment
from apps.billing.services import allocate_payment_fifo
from apps.donations.models import Donation
from apps.expenses.models import Expense
from apps.ledger.services import render_financial_report
from apps.members.models import Client, Member
from apps.members.services import compute_member_dues_amount, get_member_balance, update_member_status_from_balance


def create_member(
    *,
    membership_class: str = Member.MembershipClass.FULL,
    dues_override_cents: int | None = None,
    status: str = Member.Status.ACTIVE,
) -> Member:
    client = Client.objects.create(
        first_name="Jane",
        last_name="Doe",
        email=f"jane-{Client.objects.count() + 1}@example.org",
    )
    return Member.objects.create(
        client=client,
        membership_class=membership_class,
        dues_override_cents=dues_override_cents,
        status=status,
        joined_at=date(2026, 1, 1),
    )


def create_invoice(member: Member, invoice_number: str, issue_date: date, due_date: date, total_cents: int) -> Invoice:
    invoice = Invoice.objects.create(
        invoice_number=invoice_number,
        client=member.client,
        member=member,
        invoice_type=Invoice.InvoiceType.MEMBER_DUES,
        issue_date=issue_date,
        due_date=due_date,
        service_period_start=issue_date.replace(day=1),
        service_period_end=issue_date.replace(day=28),
        description=f"Dues for {issue_date:%B %Y}",
        total_cents=total_cents,
        external_processor=Invoice.ExternalProcessor.NONE,
    )
    InvoiceLine.objects.create(
        invoice=invoice,
        line_type=InvoiceLine.LineType.DUES,
        description=invoice.description,
        quantity=1,
        unit_price_cents=total_cents,
        line_total_cents=total_cents,
        amount_cents=total_cents,
    )
    return invoice


@pytest.mark.django_db
def test_compute_member_dues_amount_uses_class_rates_and_override(settings):
    settings.MEMBER_DUES_FULL_RATE_CENTS = 5000
    settings.MEMBER_DUES_HARDSHIP_RATE_CENTS = 2500
    full_member = create_member(membership_class=Member.MembershipClass.FULL)
    hardship_member = create_member(membership_class=Member.MembershipClass.HARDSHIP)
    override_member = create_member(dues_override_cents=4000)

    assert compute_member_dues_amount(full_member) == 5000
    assert compute_member_dues_amount(hardship_member) == 2500
    assert compute_member_dues_amount(override_member) == 4000


@pytest.mark.django_db
def test_allocate_payment_fifo_pays_oldest_invoice_first():
    member = create_member()
    older = create_invoice(member, "INV-001", date(2026, 1, 1), date(2026, 1, 15), 5000)
    newer = create_invoice(member, "INV-002", date(2026, 2, 1), date(2026, 2, 15), 5000)
    payment = Payment.objects.create(
        client=member.client,
        member=member,
        received_at="2026-02-10T12:00:00Z",
        amount_cents=7500,
        source_type=Payment.SourceType.DUES_PAYMENT,
        status=Payment.Status.SUCCEEDED,
    )

    result = allocate_payment_fifo(payment)

    older.refresh_from_db()
    newer.refresh_from_db()
    assert result.allocated_cents == 7500
    assert result.invoice_numbers == ["INV-001", "INV-002"]
    assert older.status == Invoice.Status.PAID
    assert newer.status == Invoice.Status.PARTIALLY_PAID
    assert older.allocations.get().allocated_cents == 5000
    assert newer.allocations.get().allocated_cents == 2500
    balance = get_member_balance(member, as_of=date(2026, 2, 20))
    assert balance.receivable_cents == 2500
    assert balance.credit_cents == 0


@pytest.mark.django_db
def test_enforcement_suspends_member_when_three_months_behind(settings):
    settings.ARREARS_SUSPENSION_MONTHS = 3
    settings.DUES_DUE_DAY = 15
    member = create_member(status=Member.Status.ACTIVE)
    create_invoice(member, "INV-101", date(2026, 1, 1), date(2026, 1, 15), 5000)
    create_invoice(member, "INV-102", date(2026, 2, 1), date(2026, 2, 15), 5000)
    create_invoice(member, "INV-103", date(2026, 3, 1), date(2026, 3, 15), 5000)

    balance = update_member_status_from_balance(member, as_of=date(2026, 4, 15))
    member.refresh_from_db()

    assert balance.arrears_months == 3
    assert member.status == Member.Status.SUSPENDED


@pytest.mark.django_db
def test_render_financial_report_includes_dues_cash_donations_expenses():
    member = create_member()
    invoice = create_invoice(member, "INV-201", date(2026, 4, 1), date(2026, 4, 15), 5000)
    payment = Payment.objects.create(
        client=member.client,
        member=member,
        received_at="2026-04-02T09:00:00Z",
        amount_cents=7000,
        source_type=Payment.SourceType.PREPAYMENT_TOPUP,
        status=Payment.Status.SUCCEEDED,
    )
    allocate_payment_fifo(payment)
    Donation.objects.create(
        external_charge_id="charge-1",
        donor_name="Generous Person",
        donor_email="donor@example.org",
        amount_cents=1200,
        net_amount_cents=1000,
        donation_date="2026-04-03T12:00:00Z",
        designation="Laser Cutter",
    )
    Expense.objects.create(description="Internet", booked_on=date(2026, 4, 5), amount_cents=800)

    report = render_financial_report(date(2026, 4, 1), date(2026, 4, 30))

    invoice.refresh_from_db()
    assert invoice.status == Invoice.Status.PAID
    assert report.earned_dues_cents == 5000
    assert report.cash_receipts_cents == 7000
    assert report.donations_cents == 1200
    assert report.expenses_cents == 800
    assert report.member_credit_cents == 2000
    assert report.cash_breakdown[Payment.SourceType.PREPAYMENT_TOPUP] == 7000
