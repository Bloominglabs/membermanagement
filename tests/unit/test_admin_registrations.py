from __future__ import annotations

from django.contrib import admin

from apps.billing.models import InvoiceSchedule
from apps.expenses.models import BankImportSource, ExpenseCategorizationRule, ExpenseImportBatch, ImportedBankTransaction
from apps.members.models import ClientAlias, MembershipTerm


def test_new_operational_models_are_registered_in_admin():
    for model in (
        InvoiceSchedule,
        ExpenseCategorizationRule,
        BankImportSource,
        ExpenseImportBatch,
        ImportedBankTransaction,
        ClientAlias,
        MembershipTerm,
    ):
        assert model in admin.site._registry
