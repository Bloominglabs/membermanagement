from django.contrib import admin

from apps.billing.models import (
    Allocation,
    IncomeCategory,
    Invoice,
    InvoiceLine,
    InvoiceSchedule,
    MemberBalanceSnapshot,
    Payment,
    ProcessorCustomer,
    ProcessorPaymentMethod,
    WebhookEvent,
)

admin.site.register(ProcessorCustomer)
admin.site.register(ProcessorPaymentMethod)
admin.site.register(Invoice)
admin.site.register(InvoiceLine)
admin.site.register(Payment)
admin.site.register(Allocation)
admin.site.register(MemberBalanceSnapshot)
admin.site.register(WebhookEvent)
admin.site.register(InvoiceSchedule)
admin.site.register(IncomeCategory)
