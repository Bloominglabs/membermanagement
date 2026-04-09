from __future__ import annotations

from django.db import models
from django.db.models import Q
from django.utils import timezone


class ProcessorChoices(models.TextChoices):
    STRIPE = "STRIPE", "Stripe"
    SQUARE = "SQUARE", "Square"
    BRAINTREE = "BRAINTREE", "Braintree"
    HELCIM = "HELCIM", "Helcim"
    AUTHORIZE_NET = "AUTHORIZE_NET", "Authorize.Net"


class ProcessorCustomer(models.Model):
    processor = models.CharField(max_length=20, choices=ProcessorChoices.choices)
    processor_customer_id = models.CharField(max_length=255)
    client = models.ForeignKey("members.Client", on_delete=models.CASCADE, related_name="processor_customers")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["processor", "processor_customer_id"],
                name="uniq_processor_customer_external_id",
            )
        ]
        ordering = ["processor", "processor_customer_id"]


class ProcessorPaymentMethod(models.Model):
    class MethodType(models.TextChoices):
        CARD = "card", "Card"
        ACH = "ach", "ACH"
        WALLET = "wallet", "Wallet"

    processor = models.CharField(max_length=20, choices=ProcessorChoices.choices)
    processor_payment_method_id = models.CharField(max_length=255)
    client = models.ForeignKey("members.Client", on_delete=models.CASCADE, related_name="processor_payment_methods")
    member = models.ForeignKey(
        "members.Member",
        on_delete=models.SET_NULL,
        related_name="payment_methods",
        blank=True,
        null=True,
    )
    method_type = models.CharField(max_length=20, choices=MethodType.choices)
    fingerprint_hash = models.CharField(max_length=255, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["processor", "processor_payment_method_id"],
                name="uniq_processor_payment_method_external_id",
            )
        ]
        ordering = ["-created_at", "id"]


class IncomeCategory(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]


class Invoice(models.Model):
    class InvoiceType(models.TextChoices):
        MEMBER_DUES = "MEMBER_DUES", "Member dues"
        RECURRING_AD_HOC = "RECURRING_AD_HOC", "Recurring ad-hoc"
        ONE_OFF = "ONE_OFF", "One-off"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ISSUED = "ISSUED", "Issued"
        PARTIALLY_PAID = "PARTIALLY_PAID", "Partially paid"
        PAID = "PAID", "Paid"
        VOID = "VOID", "Void"
        OVERDUE = "OVERDUE", "Overdue"

    class ExternalProcessor(models.TextChoices):
        STRIPE = "STRIPE", "Stripe"
        EVERYORG = "EVERYORG", "Every.org"
        NONE = "NONE", "None"

    invoice_type = models.CharField(max_length=30, choices=InvoiceType.choices, default=InvoiceType.ONE_OFF)
    invoice_number = models.CharField(max_length=100, unique=True)
    client = models.ForeignKey("members.Client", on_delete=models.CASCADE, related_name="invoices")
    member = models.ForeignKey(
        "members.Member",
        on_delete=models.SET_NULL,
        related_name="invoices",
        blank=True,
        null=True,
    )
    issue_date = models.DateField()
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    service_period_start = models.DateField(blank=True, null=True)
    service_period_end = models.DateField(blank=True, null=True)
    description = models.CharField(max_length=255, blank=True)
    currency = models.CharField(max_length=10, default="usd")
    total_cents = models.PositiveIntegerField(default=0)
    external_processor = models.CharField(
        max_length=20,
        choices=ExternalProcessor.choices,
        default=ExternalProcessor.NONE,
    )
    external_reference = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date", "issue_date", "invoice_number"]


class InvoiceLine(models.Model):
    class LineType(models.TextChoices):
        DUES = "DUES", "Dues"
        TOOL_FEE = "TOOL_FEE", "Tool fee"
        ROOM_FEE = "ROOM_FEE", "Room fee"
        SUPPLY = "SUPPLY", "Supply"
        OTHER = "OTHER", "Other"

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    line_type = models.CharField(max_length=20, choices=LineType.choices, default=LineType.OTHER)
    description = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price_cents = models.PositiveIntegerField(default=0)
    line_total_cents = models.PositiveIntegerField(default=0)
    amount_cents = models.PositiveIntegerField(default=0)
    income_category = models.ForeignKey(
        IncomeCategory,
        on_delete=models.SET_NULL,
        related_name="invoice_lines",
        blank=True,
        null=True,
    )
    service_period_start = models.DateField(blank=True, null=True)
    service_period_end = models.DateField(blank=True, null=True)

    class Meta:
        ordering = ["id"]


class Payment(models.Model):
    class PaymentMethod(models.TextChoices):
        STRIPE_CARD = "STRIPE_CARD", "Stripe card"
        STRIPE_ACH = "STRIPE_ACH", "Stripe ACH"
        CASH = "CASH", "Cash"
        CHECK = "CHECK", "Check"
        BANK_TRANSFER = "BANK_TRANSFER", "Bank transfer"
        EVERYORG = "EVERYORG", "Every.org"
        OTHER = "OTHER", "Other"

    class SourceType(models.TextChoices):
        DUES_PAYMENT = "DUES_PAYMENT", "Dues payment"
        PREPAYMENT_TOPUP = "PREPAYMENT_TOPUP", "Prepayment top-up"
        ARREARS_CATCHUP = "ARREARS_CATCHUP", "Arrears catch-up"
        DONATION = "DONATION", "Donation"
        OTHER_INCOME = "OTHER_INCOME", "Other income"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"
        REFUNDED = "REFUNDED", "Refunded"
        REVERSED = "REVERSED", "Reversed"

    client = models.ForeignKey("members.Client", on_delete=models.CASCADE, related_name="payments")
    member = models.ForeignKey(
        "members.Member",
        on_delete=models.SET_NULL,
        related_name="payments",
        blank=True,
        null=True,
    )
    received_at = models.DateTimeField(default=timezone.now)
    amount_cents = models.PositiveIntegerField()
    currency = models.CharField(max_length=10, default="usd")
    payment_method = models.CharField(max_length=30, choices=PaymentMethod.choices, default=PaymentMethod.OTHER)
    source_type = models.CharField(max_length=30, choices=SourceType.choices)
    processor = models.CharField(max_length=20, choices=ProcessorChoices.choices, blank=True, null=True)
    processor_event_id = models.CharField(max_length=255, blank=True, null=True)
    processor_charge_id = models.CharField(max_length=255, blank=True, null=True)
    processor_payment_id = models.CharField(max_length=255, blank=True, null=True)
    processor_balance_txn_id = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-received_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["processor", "processor_payment_id"],
                condition=Q(processor__isnull=False) & Q(processor_payment_id__isnull=False),
                name="uniq_processor_payment_id",
            )
        ]


class Allocation(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="allocations")
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="allocations")
    invoice_line = models.ForeignKey(
        InvoiceLine,
        on_delete=models.SET_NULL,
        related_name="allocations",
        blank=True,
        null=True,
    )
    allocated_cents = models.PositiveIntegerField()
    allocated_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["allocated_at", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(allocated_cents__gt=0), name="allocation_positive_cents"),
        ]


class MemberBalanceSnapshot(models.Model):
    member = models.ForeignKey("members.Member", on_delete=models.CASCADE, related_name="balance_snapshots")
    as_of = models.DateField()
    credit_cents = models.IntegerField()
    receivable_cents = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-as_of", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["member", "as_of"], name="uniq_member_balance_snapshot"),
        ]


class WebhookEvent(models.Model):
    processor = models.CharField(max_length=20, choices=ProcessorChoices.choices)
    event_id = models.CharField(max_length=255)
    received_at = models.DateTimeField(auto_now_add=True)
    payload_json = models.JSONField(default=dict)
    signature_valid = models.BooleanField(default=False)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-received_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["processor", "event_id"], name="uniq_webhook_processor_event_id"),
        ]


class MemberCreditLedger(models.Model):
    class EntryType(models.TextChoices):
        PAYMENT_IN = "PAYMENT_IN", "Payment in"
        CHARGE_OUT = "CHARGE_OUT", "Charge out"
        MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT", "Manual adjustment"
        REVERSAL = "REVERSAL", "Reversal"

    member = models.ForeignKey("members.Member", on_delete=models.CASCADE, related_name="credit_ledger_entries")
    entry_type = models.CharField(max_length=30, choices=EntryType.choices)
    delta_cents = models.IntegerField()
    effective_at = models.DateTimeField(default=timezone.now)
    reference_type = models.CharField(max_length=50, blank=True)
    reference_id = models.CharField(max_length=100, blank=True)
    memo = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["effective_at", "id"]


class InvoiceSchedule(models.Model):
    class Frequency(models.TextChoices):
        MONTHLY = "MONTHLY", "Monthly"
        QUARTERLY = "QUARTERLY", "Quarterly"
        ANNUAL = "ANNUAL", "Annual"
        ONE_OFF = "ONE_OFF", "One-off"

    client = models.ForeignKey("members.Client", on_delete=models.CASCADE, related_name="invoice_schedules")
    member = models.ForeignKey(
        "members.Member",
        on_delete=models.SET_NULL,
        related_name="invoice_schedules",
        blank=True,
        null=True,
    )
    invoice_type = models.CharField(max_length=30, choices=Invoice.InvoiceType.choices, default=Invoice.InvoiceType.ONE_OFF)
    description = models.CharField(max_length=255)
    frequency = models.CharField(max_length=20, choices=Frequency.choices, default=Frequency.MONTHLY)
    generation_day = models.PositiveSmallIntegerField(blank=True, null=True)
    due_day = models.PositiveSmallIntegerField(blank=True, null=True)
    due_offset_days = models.PositiveSmallIntegerField(blank=True, null=True)
    amount_cents = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    last_issued_on = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["client_id", "id"]
