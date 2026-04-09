from django.contrib import admin

from apps.expenses.models import (
    BankImportSource,
    Expense,
    ExpenseCategorizationRule,
    ExpenseCategory,
    ExpenseImportBatch,
    ImportedBankTransaction,
)

admin.site.register(ExpenseCategory)
admin.site.register(Expense)
admin.site.register(ExpenseCategorizationRule)
admin.site.register(BankImportSource)
admin.site.register(ExpenseImportBatch)
admin.site.register(ImportedBankTransaction)
