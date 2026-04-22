from __future__ import annotations

from django import forms

from apps.billing.models import Payment

MANUAL_PAYMENT_METHOD_CHOICES = [
    (Payment.PaymentMethod.CASH, "Cash"),
    (Payment.PaymentMethod.CHECK, "Check"),
    (Payment.PaymentMethod.BANK_TRANSFER, "Bank transfer"),
    (Payment.PaymentMethod.OTHER, "Other"),
]


class ManualPaymentForm(forms.Form):
    amount_cents = forms.IntegerField(min_value=1)
    payment_method = forms.ChoiceField(choices=MANUAL_PAYMENT_METHOD_CHOICES, required=False)
    source_type = forms.ChoiceField(choices=Payment.SourceType.choices)
    note = forms.CharField(required=False)


class OneOffInvoiceForm(forms.Form):
    invoice_number = forms.CharField(max_length=100)
    description = forms.CharField(max_length=255)
    amount_cents = forms.IntegerField(min_value=1)


class RFIDCredentialForm(forms.Form):
    uid = forms.CharField(max_length=255)
    label = forms.CharField(max_length=100, required=False)


class DoorAccessForm(forms.Form):
    door_access_enabled = forms.BooleanField(required=False)


class BillingRunForm(forms.Form):
    ACTION_MONTHLY_DUES_CLOSE = "monthly_dues_close"
    ACTION_SCHEDULED_INVOICES = "scheduled_invoice_generation"
    ACTION_AUTOPAY = "dues_autopay_run"
    ACTION_ENFORCEMENT = "enforcement_run"
    ACTION_RECONCILIATION = "stripe_reconciliation_sync"

    action = forms.ChoiceField(
        choices=[
            (ACTION_MONTHLY_DUES_CLOSE, "Monthly dues close"),
            (ACTION_SCHEDULED_INVOICES, "Scheduled invoice generation"),
            (ACTION_AUTOPAY, "Autopay run"),
            (ACTION_ENFORCEMENT, "Status enforcement"),
            (ACTION_RECONCILIATION, "Stripe reconciliation sync"),
        ]
    )


class ExpenseImportForm(forms.Form):
    source_name = forms.CharField(max_length=100)
    parser_key = forms.CharField(max_length=100)
    csv_content = forms.CharField(widget=forms.Textarea)


class ExpenseCategorizeForm(forms.Form):
    category_code = forms.CharField(max_length=50)
    category_name = forms.CharField(max_length=100)
    reconciled = forms.BooleanField(required=False)


class ReportFilterForm(forms.Form):
    from_date = forms.DateField(input_formats=["%Y-%m-%d"], required=True)
    to_date = forms.DateField(input_formats=["%Y-%m-%d"], required=True)


class AuditFilterForm(forms.Form):
    entity_type = forms.CharField(max_length=100, required=False)
    entity_id = forms.CharField(max_length=100, required=False)
    action = forms.CharField(max_length=100, required=False)
    actor = forms.CharField(max_length=255, required=False)
    occurred_from = forms.DateField(input_formats=["%Y-%m-%d"], required=False)
    occurred_to = forms.DateField(input_formats=["%Y-%m-%d"], required=False)
