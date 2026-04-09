from __future__ import annotations

import re

from django.db import transaction

from apps.expenses.models import Expense, ExpenseCategory, ExpenseCategorizationRule, ImportedBankTransaction


def _matches_vendor(rule: ExpenseCategorizationRule, transaction: ImportedBankTransaction) -> bool:
    if not rule.vendor_name:
        return True
    return rule.vendor_name.lower() in transaction.description_raw.lower()


def _matches_amount_range(pattern: str, amount_cents: int) -> bool:
    raw_min, _, raw_max = pattern.partition(":")
    if not _:
        return False
    lower = int(raw_min) if raw_min.strip() else None
    upper = int(raw_max) if raw_max.strip() else None
    amount = abs(amount_cents)
    if lower is not None and amount < lower:
        return False
    if upper is not None and amount > upper:
        return False
    return True


def rule_matches_transaction(rule: ExpenseCategorizationRule, transaction: ImportedBankTransaction) -> bool:
    if not rule.active or not _matches_vendor(rule, transaction):
        return False
    description = transaction.description_raw
    if rule.match_type == ExpenseCategorizationRule.MatchType.CONTAINS:
        return rule.pattern.lower() in description.lower()
    if rule.match_type == ExpenseCategorizationRule.MatchType.REGEX:
        return bool(re.search(rule.pattern, description, flags=re.IGNORECASE))
    if rule.match_type == ExpenseCategorizationRule.MatchType.AMOUNT_RANGE:
        return _matches_amount_range(rule.pattern, transaction.amount_cents)
    return False


def find_categorization_rule(transaction: ImportedBankTransaction) -> ExpenseCategorizationRule | None:
    for rule in ExpenseCategorizationRule.objects.select_related("expense_category").filter(active=True).order_by("priority", "id"):
        if rule_matches_transaction(rule, transaction):
            return rule
    return None


@transaction.atomic
def categorize_imported_transaction(
    transaction_record: ImportedBankTransaction,
    category: ExpenseCategory,
    *,
    reconciled: bool = False,
) -> Expense:
    expense = transaction_record.expense
    if expense is None:
        expense = Expense.objects.create(
            description=transaction_record.description_raw,
            booked_on=transaction_record.posted_on,
            amount_cents=abs(transaction_record.amount_cents),
            category=category,
            review_status=Expense.ReviewStatus.CATEGORIZED,
        )
    else:
        changed_fields: list[str] = []
        if expense.category_id != category.id:
            expense.category = category
            changed_fields.append("category")
        if expense.review_status != Expense.ReviewStatus.CATEGORIZED:
            expense.review_status = Expense.ReviewStatus.CATEGORIZED
            changed_fields.append("review_status")
        if changed_fields:
            expense.save(update_fields=changed_fields)

    transaction_fields: list[str] = []
    if transaction_record.expense_id != expense.id:
        transaction_record.expense = expense
        transaction_fields.append("expense")
    if transaction_record.is_reconciled != reconciled:
        transaction_record.is_reconciled = reconciled
        transaction_fields.append("is_reconciled")
    if transaction_fields:
        transaction_record.save(update_fields=transaction_fields)
    return expense


def auto_categorize_imported_transaction(transaction_record: ImportedBankTransaction) -> Expense | None:
    rule = find_categorization_rule(transaction_record)
    if not rule:
        return None
    return categorize_imported_transaction(transaction_record, rule.expense_category, reconciled=False)
