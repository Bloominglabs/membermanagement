from __future__ import annotations

from datetime import date

import pytest

from apps.billing.models import Invoice, InvoiceLine, InvoiceSchedule, MemberCreditLedger, Payment
from apps.billing.services import (
    allocate_payment_fifo,
    calculate_due_date,
    generate_due_scheduled_invoices,
    generate_invoice_from_schedule,
)
from apps.members.models import Client, Member


def create_member() -> Member:
    client = Client.objects.create(
        client_type=Client.ClientType.PERSON,
        display_name_text=f"Member {Client.objects.count() + 1}",
        email=f"member-{Client.objects.count() + 1}@example.org",
    )
    return Member.objects.create(
        client=client,
        status=Member.Status.ACTIVE,
        membership_class=Member.MembershipClass.FULL,
        voting_eligible=True,
        joined_at="2026-01-01",
    )


@pytest.mark.django_db
def test_calculate_due_date_supports_due_day_and_offset():
    issue_date = date(2026, 4, 3)

    assert calculate_due_date(issue_date, due_day=15) == date(2026, 4, 15)
    assert calculate_due_date(issue_date, due_offset_days=14) == date(2026, 4, 17)


@pytest.mark.django_db
def test_member_credit_ledger_tracks_payment_in_and_charge_out():
    member = create_member()
    invoice = Invoice.objects.create(
        client=member.client,
        member=member,
        invoice_type=Invoice.InvoiceType.MEMBER_DUES,
        invoice_number="INV-CL-001",
        issue_date="2026-04-01",
        due_date="2026-04-15",
        service_period_start="2026-04-01",
        service_period_end="2026-04-30",
        status=Invoice.Status.ISSUED,
        total_cents=5000,
        external_processor=Invoice.ExternalProcessor.NONE,
    )
    InvoiceLine.objects.create(
        invoice=invoice,
        line_type=InvoiceLine.LineType.DUES,
        description="April dues",
        quantity=1,
        unit_price_cents=5000,
        line_total_cents=5000,
    )
    payment = Payment.objects.create(
        client=member.client,
        member=member,
        amount_cents=7000,
        source_type=Payment.SourceType.PREPAYMENT_TOPUP,
        payment_method=Payment.PaymentMethod.CASH,
        status=Payment.Status.SUCCEEDED,
    )

    allocate_payment_fifo(payment)

    ledger_entries = list(MemberCreditLedger.objects.filter(member=member).order_by("effective_at", "id"))
    assert [entry.entry_type for entry in ledger_entries] == [
        MemberCreditLedger.EntryType.PAYMENT_IN,
        MemberCreditLedger.EntryType.CHARGE_OUT,
    ]
    assert ledger_entries[0].delta_cents == 7000
    assert ledger_entries[1].delta_cents == -5000


@pytest.mark.django_db
def test_generate_invoice_from_schedule_supports_due_offset():
    member = create_member()
    schedule = InvoiceSchedule.objects.create(
        client=member.client,
        member=member,
        invoice_type=Invoice.InvoiceType.RECURRING_AD_HOC,
        description="Quarterly tool fee",
        frequency=InvoiceSchedule.Frequency.QUARTERLY,
        generation_day=10,
        due_offset_days=20,
        amount_cents=12000,
    )

    invoice = generate_invoice_from_schedule(schedule, issue_date=date(2026, 4, 10))

    assert invoice.invoice_type == Invoice.InvoiceType.RECURRING_AD_HOC
    assert invoice.issue_date == date(2026, 4, 10)
    assert invoice.due_date == date(2026, 4, 30)
    assert invoice.total_cents == 12000


@pytest.mark.django_db
def test_generate_due_scheduled_invoices_respects_frequency_generation_day_and_idempotency():
    member = create_member()
    monthly = InvoiceSchedule.objects.create(
        client=member.client,
        member=member,
        invoice_type=Invoice.InvoiceType.RECURRING_AD_HOC,
        description="Monthly room fee",
        frequency=InvoiceSchedule.Frequency.MONTHLY,
        generation_day=5,
        due_offset_days=10,
        amount_cents=3000,
    )
    quarterly = InvoiceSchedule.objects.create(
        client=member.client,
        member=member,
        invoice_type=Invoice.InvoiceType.RECURRING_AD_HOC,
        description="Quarterly tool fee",
        frequency=InvoiceSchedule.Frequency.QUARTERLY,
        generation_day=10,
        due_day=20,
        amount_cents=12000,
    )

    assert generate_due_scheduled_invoices(run_date=date(2026, 4, 4)) == []

    april_invoices = generate_due_scheduled_invoices(run_date=date(2026, 4, 20))
    repeat_april_invoices = generate_due_scheduled_invoices(run_date=date(2026, 4, 21))
    may_invoices = generate_due_scheduled_invoices(run_date=date(2026, 5, 20))
    july_invoices = generate_due_scheduled_invoices(run_date=date(2026, 7, 10))

    assert [invoice.invoice_number for invoice in april_invoices] == [
        f"SCH-{monthly.pk}-20260405",
        f"SCH-{quarterly.pk}-20260410",
    ]
    assert repeat_april_invoices == []
    assert [invoice.invoice_number for invoice in may_invoices] == [f"SCH-{monthly.pk}-20260505"]
    assert [invoice.invoice_number for invoice in july_invoices] == [
        f"SCH-{monthly.pk}-20260705",
        f"SCH-{quarterly.pk}-20260710",
    ]
