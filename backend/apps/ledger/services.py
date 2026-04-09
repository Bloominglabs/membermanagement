from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce

from apps.billing.models import Invoice, Payment
from apps.donations.models import Donation
from apps.expenses.models import Expense
from apps.ledger.models import Account, JournalEntry, JournalLine


DEFAULT_ACCOUNTS = {
    "1100": ("Accounts Receivable", Account.Kind.ASSET),
    "1110": ("Stripe Clearing", Account.Kind.ASSET),
    "1120": ("Cash", Account.Kind.ASSET),
    "2100": ("Member Credit Liability", Account.Kind.LIABILITY),
    "4100": ("Membership Dues Income", Account.Kind.INCOME),
    "4200": ("Donations Income", Account.Kind.INCOME),
    "5100": ("Operating Expenses", Account.Kind.EXPENSE),
}


@dataclass(slots=True)
class FinancialReport:
    start: date
    end: date
    earned_dues_cents: int
    cash_receipts_cents: int
    donations_cents: int
    expenses_cents: int
    outstanding_receivables_cents: int
    member_credit_cents: int
    cash_breakdown: dict[str, int]
    summary: dict[str, Any]
    dues: dict[str, Any]
    donations: dict[str, Any]
    expenses: dict[str, Any]
    balance_snapshot: dict[str, Any]


def ensure_default_accounts() -> dict[str, Account]:
    accounts: dict[str, Account] = {}
    for code, (name, kind) in DEFAULT_ACCOUNTS.items():
        account, _ = Account.objects.get_or_create(code=code, defaults={"name": name, "kind": kind})
        accounts[code] = account
    return accounts


@transaction.atomic
def create_balanced_entry(
    *,
    occurred_on: date,
    description: str,
    reference: str,
    source_type: str,
    source_id: str,
    lines: list[tuple[str, str, int, str]],
) -> JournalEntry:
    debit_total = sum(amount for _, entry_type, amount, _ in lines if entry_type == JournalLine.EntryType.DEBIT)
    credit_total = sum(amount for _, entry_type, amount, _ in lines if entry_type == JournalLine.EntryType.CREDIT)
    if debit_total != credit_total:
        raise ValueError("Journal entry is not balanced.")

    existing = JournalEntry.objects.filter(source_type=source_type, source_id=source_id).first()
    if existing:
        return existing

    accounts = ensure_default_accounts()
    entry = JournalEntry.objects.create(
        occurred_on=occurred_on,
        description=description,
        reference=reference,
        source_type=source_type,
        source_id=source_id,
    )
    JournalLine.objects.bulk_create(
        [
            JournalLine(
                journal_entry=entry,
                account=accounts[account_code],
                entry_type=entry_type,
                amount_cents=amount_cents,
                memo=memo,
            )
            for account_code, entry_type, amount_cents, memo in lines
        ]
    )
    return entry


def post_dues_invoice(invoice: Invoice) -> JournalEntry:
    return create_balanced_entry(
        occurred_on=invoice.issue_date,
        description=f"Dues invoice {invoice.invoice_number}",
        reference=invoice.invoice_number,
        source_type="invoice",
        source_id=str(invoice.pk),
        lines=[
            ("1100", JournalLine.EntryType.DEBIT, invoice.total_cents, invoice.description),
            ("4100", JournalLine.EntryType.CREDIT, invoice.total_cents, invoice.description),
        ],
    )


def post_payment(payment: Payment) -> JournalEntry | None:
    if payment.status != Payment.Status.SUCCEEDED:
        return None
    allocated = payment.allocations.aggregate(total=Coalesce(Sum("allocated_cents"), 0)).get("total", 0)
    unapplied = max(payment.amount_cents - allocated, 0)
    bank_account = "1110" if payment.processor else "1120"
    lines: list[tuple[str, str, int, str]] = [
        (bank_account, JournalLine.EntryType.DEBIT, payment.amount_cents, payment.notes or payment.get_source_type_display())
    ]
    if allocated:
        lines.append(("1100", JournalLine.EntryType.CREDIT, allocated, "Applied against receivable"))
    if unapplied:
        lines.append(("2100", JournalLine.EntryType.CREDIT, unapplied, "Held as member credit"))
    return create_balanced_entry(
        occurred_on=payment.received_at.date(),
        description=f"Payment {payment.pk}",
        reference=payment.processor_payment_id or str(payment.pk),
        source_type="payment",
        source_id=str(payment.pk),
        lines=lines,
    )


def render_financial_report(start: date, end: date) -> FinancialReport:
    dues_invoices = Invoice.objects.filter(
        invoice_type=Invoice.InvoiceType.MEMBER_DUES,
        service_period_start__gte=start,
        service_period_end__lte=end,
    ).exclude(status=Invoice.Status.VOID)
    earned_dues_cents = sum(
        invoice.allocations.filter(
            payment__status=Payment.Status.SUCCEEDED,
            payment__received_at__date__gte=start,
            payment__received_at__date__lte=end,
        ).aggregate(total=Coalesce(Sum("allocated_cents"), 0)).get("total", 0)
        for invoice in dues_invoices
    )
    dues_invoiced_cents = dues_invoices.aggregate(total=Coalesce(Sum("total_cents"), 0)).get("total", 0)
    cash_receipts = (
        Payment.objects.filter(status=Payment.Status.SUCCEEDED, received_at__date__gte=start, received_at__date__lte=end)
        .aggregate(total=Coalesce(Sum("amount_cents"), 0))
        .get("total", 0)
    )
    donations = (
        Donation.objects.filter(donation_date__date__gte=start, donation_date__date__lte=end)
        .aggregate(total=Coalesce(Sum("amount_cents"), 0))
        .get("total", 0)
    )
    expenses = (
        Expense.objects.filter(booked_on__gte=start, booked_on__lte=end)
        .aggregate(total=Coalesce(Sum("amount_cents"), 0))
        .get("total", 0)
    )
    outstanding_receivables = 0
    for invoice in Invoice.objects.exclude(status=Invoice.Status.VOID):
        paid = invoice.allocations.filter(payment__status=Payment.Status.SUCCEEDED).aggregate(
            total=Coalesce(Sum("allocated_cents"), 0)
        ).get("total", 0)
        outstanding_receivables += max(invoice.total_cents - paid, 0)
    member_credit = 0
    for payment in Payment.objects.filter(status=Payment.Status.SUCCEEDED):
        applied = payment.allocations.aggregate(total=Coalesce(Sum("allocated_cents"), 0)).get("total", 0)
        member_credit += max(payment.amount_cents - applied, 0)
    breakdown_rows = (
        Payment.objects.filter(status=Payment.Status.SUCCEEDED, received_at__date__gte=start, received_at__date__lte=end)
        .values_list("source_type")
        .annotate(total=Coalesce(Sum("amount_cents"), 0))
    )
    breakdown = {source_type: total for source_type, total in breakdown_rows}
    payments_in_window = Payment.objects.filter(status=Payment.Status.SUCCEEDED, received_at__date__gte=start, received_at__date__lte=end)
    member_prepayments_received_cents = (
        payments_in_window.filter(source_type=Payment.SourceType.PREPAYMENT_TOPUP)
        .aggregate(total=Coalesce(Sum("amount_cents"), 0))
        .get("total", 0)
    )
    debt_repayments_received_cents = (
        payments_in_window.filter(source_type=Payment.SourceType.ARREARS_CATCHUP)
        .aggregate(total=Coalesce(Sum("amount_cents"), 0))
        .get("total", 0)
    )
    dues_cash_received_cents = (
        payments_in_window.filter(source_type=Payment.SourceType.DUES_PAYMENT)
        .aggregate(total=Coalesce(Sum("amount_cents"), 0))
        .get("total", 0)
    )
    other_income_received_cents = (
        payments_in_window.filter(source_type=Payment.SourceType.OTHER_INCOME)
        .aggregate(total=Coalesce(Sum("amount_cents"), 0))
        .get("total", 0)
    )
    categorized_expenses_cents = (
        Expense.objects.filter(booked_on__gte=start, booked_on__lte=end, category__isnull=False)
        .aggregate(total=Coalesce(Sum("amount_cents"), 0))
        .get("total", 0)
    )
    expense_rows = (
        Expense.objects.filter(booked_on__gte=start, booked_on__lte=end, category__isnull=False)
        .values_list("category__code")
        .annotate(total=Coalesce(Sum("amount_cents"), 0))
    )
    expenses_by_category = {category_code: total for category_code, total in expense_rows}
    uncategorized_expenses_cents = max(expenses - categorized_expenses_cents, 0)
    reconciled_expense_count = Expense.objects.filter(
        booked_on__gte=start,
        booked_on__lte=end,
        review_status=Expense.ReviewStatus.RECONCILED,
    ).count()
    unreconciled_expense_count = Expense.objects.filter(
        booked_on__gte=start,
        booked_on__lte=end,
    ).exclude(review_status=Expense.ReviewStatus.RECONCILED).count()
    donations_by_designation = {}
    anonymous_count = 0
    identified_count = 0
    for donation in Donation.objects.filter(donation_date__date__gte=start, donation_date__date__lte=end):
        donations_by_designation[donation.designation or "Unspecified"] = (
            donations_by_designation.get(donation.designation or "Unspecified", 0) + donation.amount_cents
        )
        if donation.donor_email or donation.donor_name:
            identified_count += 1
        else:
            anonymous_count += 1
    cash_in_cents = cash_receipts + donations
    cash_out_cents = expenses
    net_cashflow_cents = cash_in_cents - cash_out_cents
    prepayment_balance_carried_in = member_credit
    prepayment_balance_carried_out = member_credit
    debt_balance_carried_in = outstanding_receivables
    debt_balance_carried_out = outstanding_receivables
    balance_snapshot = {
        "bank_asset_balance_cents": max(cash_receipts - expenses, 0),
        "stripe_clearing_balance_cents": Payment.objects.filter(
            processor__isnull=False,
            status=Payment.Status.SUCCEEDED,
            processor_balance_txn_id__isnull=True,
        ).aggregate(total=Coalesce(Sum("amount_cents"), 0)).get("total", 0),
        "accounts_receivable_cents": outstanding_receivables,
        "member_prepayment_liability_cents": member_credit,
    }
    return FinancialReport(
        start=start,
        end=end,
        earned_dues_cents=earned_dues_cents,
        cash_receipts_cents=cash_receipts,
        donations_cents=donations,
        expenses_cents=expenses,
        outstanding_receivables_cents=outstanding_receivables,
        member_credit_cents=member_credit,
        cash_breakdown=breakdown,
        summary={
            "cash_in_cents": cash_in_cents,
            "cash_out_cents": cash_out_cents,
            "net_cashflow_cents": net_cashflow_cents,
            "earned_dues_cents": earned_dues_cents,
            "dues_cash_received_cents": dues_cash_received_cents,
            "member_prepayments_received_cents": member_prepayments_received_cents,
            "debt_repayments_received_cents": debt_repayments_received_cents,
            "donations_received_cents": donations,
            "other_income_received_cents": other_income_received_cents,
            "expenses_by_category_cents": expenses_by_category,
        },
        dues={
            "dues_invoiced_cents": dues_invoiced_cents,
            "dues_paid_cents": earned_dues_cents,
            "unpaid_dues_outstanding_cents": outstanding_receivables,
            "prepayment_balance_carried_in_cents": prepayment_balance_carried_in,
            "prepayment_balance_carried_out_cents": prepayment_balance_carried_out,
            "debt_balance_carried_in_cents": debt_balance_carried_in,
            "debt_balance_carried_out_cents": debt_balance_carried_out,
        },
        donations={
            "total_donations_cents": donations,
            "by_designation": donations_by_designation,
            "anonymous_count": anonymous_count,
            "identified_count": identified_count,
        },
        expenses={
            "categorized_expenses_cents": categorized_expenses_cents,
            "uncategorized_expenses_cents": uncategorized_expenses_cents,
            "by_category_cents": expenses_by_category,
            "reconciled_count": reconciled_expense_count,
            "unreconciled_count": unreconciled_expense_count,
        },
        balance_snapshot=balance_snapshot,
    )
