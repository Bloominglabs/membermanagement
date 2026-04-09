from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from api.views import (
    ARAgingReportView,
    AccessEventView,
    AllowlistView,
    ClientViewSet,
    DonationViewSet,
    EveryOrgWebhookView,
    ExpenseCategorizeView,
    ExpenseImportBatchListView,
    ExpenseImportCsvView,
    FinancialReportCsvView,
    FinancialReportView,
    InvoiceViewSet,
    ManualPaymentEntryView,
    MemberEntitlementView,
    MemberBalancesReportView,
    MemberBalancesCsvView,
    MemberViewSet,
    PaymentViewSet,
    StripeCheckoutSessionView,
    StripeSetupIntentView,
    StripeWebhookView,
)

router = DefaultRouter()
router.register("clients", ClientViewSet, basename="clients")
router.register("donations", DonationViewSet, basename="donations")
router.register("invoices", InvoiceViewSet, basename="invoices")
router.register("members", MemberViewSet, basename="members")
router.register("payments", PaymentViewSet, basename="payments")

urlpatterns = [
    path("api/", include(router.urls)),
    path("api/members/<int:pk>/history", MemberViewSet.as_view({"get": "history"})),
    path("api/invoices/<int:pk>/issue", InvoiceViewSet.as_view({"post": "issue"})),
    path("api/invoices/<int:pk>/void", InvoiceViewSet.as_view({"post": "void"})),
    path("api/payments/manual", ManualPaymentEntryView.as_view()),
    path("api/payments/<int:pk>/allocate", PaymentViewSet.as_view({"post": "allocate"})),
    path("api/donations/manual", DonationViewSet.as_view({"post": "create"})),
    path("api/donations", DonationViewSet.as_view({"get": "list"})),
    path("api/expenses/import/csv", ExpenseImportCsvView.as_view()),
    path("api/expenses/import-batches", ExpenseImportBatchListView.as_view()),
    path("api/expenses/<int:transaction_id>/categorize", ExpenseCategorizeView.as_view()),
    path("api/billing/stripe/create-checkout-session/", StripeCheckoutSessionView.as_view()),
    path("api/billing/stripe/create-setup-intent/", StripeSetupIntentView.as_view()),
    path("api/stripe/create-checkout-session", StripeCheckoutSessionView.as_view()),
    path("api/stripe/create-setup-intent", StripeSetupIntentView.as_view()),
    path("webhooks/stripe/", StripeWebhookView.as_view()),
    path("webhooks/everyorg/nonprofit-donation/", EveryOrgWebhookView.as_view()),
    path("api/access/allowlist/", AllowlistView.as_view()),
    path("api/access/members/<int:member_id>/entitlement", MemberEntitlementView.as_view()),
    path("api/access/events/", AccessEventView.as_view()),
    path("api/reports/financial", FinancialReportView.as_view()),
    path("api/reports/member-balances", MemberBalancesReportView.as_view()),
    path("api/reports/ar-aging", ARAgingReportView.as_view()),
    path("api/exports/financial.csv", FinancialReportCsvView.as_view()),
    path("api/exports/member-balances.csv", MemberBalancesCsvView.as_view()),
]
