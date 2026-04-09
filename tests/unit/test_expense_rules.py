from __future__ import annotations

import pytest

from apps.expenses.models import (
    BankImportSource,
    ExpenseCategory,
    ExpenseCategorizationRule,
    ExpenseImportBatch,
    ImportedBankTransaction,
)
from apps.expenses.services import auto_categorize_imported_transaction, find_categorization_rule


def create_transaction(*, description: str, amount_cents: int) -> ImportedBankTransaction:
    source = BankImportSource.objects.create(name="Checking", parser_key="csv")
    batch = ExpenseImportBatch.objects.create(source=source)
    return ImportedBankTransaction.objects.create(
        source=source,
        import_batch=batch,
        posted_on="2026-04-08",
        description_raw=description,
        amount_cents=amount_cents,
        direction=ImportedBankTransaction.Direction.DEBIT,
        currency="usd",
        external_hash=f"{description}-{amount_cents}",
    )


@pytest.mark.django_db
def test_find_categorization_rule_prefers_priority_order_across_match_types():
    internet = ExpenseCategory.objects.create(code="INTERNET", name="Internet")
    tools = ExpenseCategory.objects.create(code="TOOLS", name="Tools")
    ExpenseCategorizationRule.objects.create(
        priority=20,
        match_type=ExpenseCategorizationRule.MatchType.REGEX,
        pattern="internet provider",
        expense_category=internet,
    )
    preferred = ExpenseCategorizationRule.objects.create(
        priority=10,
        match_type=ExpenseCategorizationRule.MatchType.CONTAINS,
        pattern="internet",
        expense_category=tools,
    )
    transaction = create_transaction(description="Internet Provider Invoice", amount_cents=800)

    match = find_categorization_rule(transaction)

    assert match is not None
    assert match.pk == preferred.pk


@pytest.mark.django_db
def test_auto_categorize_imported_transaction_supports_amount_range_rule():
    utilities = ExpenseCategory.objects.create(code="UTIL", name="Utilities")
    ExpenseCategorizationRule.objects.create(
        priority=5,
        match_type=ExpenseCategorizationRule.MatchType.AMOUNT_RANGE,
        pattern="700:900",
        expense_category=utilities,
    )
    transaction = create_transaction(description="Unknown Vendor", amount_cents=800)

    expense = auto_categorize_imported_transaction(transaction)
    transaction.refresh_from_db()

    assert expense is not None
    assert expense.category == utilities
    assert transaction.expense == expense
    assert transaction.is_reconciled is False
