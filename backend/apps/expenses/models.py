from __future__ import annotations

from django.db import models


class BankImportSource(models.Model):
    name = models.CharField(max_length=100)
    parser_key = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]


class ExpenseImportBatch(models.Model):
    source = models.ForeignKey(BankImportSource, on_delete=models.CASCADE, related_name="import_batches")
    imported_at = models.DateTimeField(auto_now_add=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-imported_at", "-id"]


class ExpenseCategory(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class Expense(models.Model):
    class ReviewStatus(models.TextChoices):
        UNREVIEWED = "UNREVIEWED", "Unreviewed"
        CATEGORIZED = "CATEGORIZED", "Categorized"
        RECONCILED = "RECONCILED", "Reconciled"

    external_id = models.CharField(max_length=255, blank=True)
    description = models.CharField(max_length=255)
    booked_on = models.DateField()
    amount_cents = models.PositiveIntegerField()
    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.SET_NULL,
        related_name="expenses",
        blank=True,
        null=True,
    )
    review_status = models.CharField(max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.UNREVIEWED)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-booked_on", "-id"]


class ImportedBankTransaction(models.Model):
    class Direction(models.TextChoices):
        DEBIT = "DEBIT", "Debit"
        CREDIT = "CREDIT", "Credit"

    source = models.ForeignKey(BankImportSource, on_delete=models.CASCADE, related_name="transactions")
    import_batch = models.ForeignKey(ExpenseImportBatch, on_delete=models.CASCADE, related_name="transactions")
    posted_on = models.DateField()
    description_raw = models.CharField(max_length=255)
    amount_cents = models.IntegerField()
    direction = models.CharField(max_length=10, choices=Direction.choices)
    currency = models.CharField(max_length=10, default="usd")
    external_hash = models.CharField(max_length=255, unique=True)
    is_duplicate = models.BooleanField(default=False)
    is_reconciled = models.BooleanField(default=False)
    expense = models.ForeignKey(
        Expense,
        on_delete=models.SET_NULL,
        related_name="imported_transactions",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-posted_on", "-id"]


class ExpenseCategorizationRule(models.Model):
    class MatchType(models.TextChoices):
        REGEX = "REGEX", "Regex"
        CONTAINS = "CONTAINS", "Contains"
        AMOUNT_RANGE = "AMOUNT_RANGE", "Amount range"

    priority = models.PositiveIntegerField(default=100)
    match_type = models.CharField(max_length=20, choices=MatchType.choices)
    pattern = models.CharField(max_length=255)
    expense_category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.CASCADE,
        related_name="categorization_rules",
    )
    vendor_name = models.CharField(max_length=255, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["priority", "id"]
