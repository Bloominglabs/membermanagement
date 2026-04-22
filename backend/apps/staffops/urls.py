from __future__ import annotations

from django.urls import path

from apps.staffops import views


app_name = "staffops"


urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.global_search, name="global-search"),
    path("members/", views.member_list, name="member-list"),
    path("members/<int:member_id>/", views.member_workspace, name="member-workspace"),
    path("members/<int:member_id>/manual-payment/", views.member_manual_payment, name="member-manual-payment"),
    path("members/<int:member_id>/one-off-invoices/", views.member_one_off_invoice, name="member-one-off-invoice"),
    path("members/<int:member_id>/rfid/add/", views.member_add_rfid, name="member-add-rfid"),
    path(
        "members/<int:member_id>/rfid/<int:credential_id>/deactivate/",
        views.member_deactivate_rfid,
        name="member-deactivate-rfid",
    ),
    path("members/<int:member_id>/door-access/", views.member_update_door_access, name="member-door-access"),
    path("billing/", views.billing_dashboard, name="billing-dashboard"),
    path("billing/run/", views.billing_run, name="billing-run"),
    path("billing/invoices/", views.invoice_review, name="invoice-review"),
    path("billing/invoices/bulk-action/", views.invoice_bulk_action, name="invoice-bulk-action"),
    path("billing/invoices/<int:invoice_id>/issue/", views.invoice_issue_action, name="invoice-issue"),
    path("billing/invoices/<int:invoice_id>/void/", views.invoice_void_action, name="invoice-void"),
    path("billing/payments/", views.payment_review, name="payment-review"),
    path("billing/payments/<int:payment_id>/allocate/", views.payment_allocate_action, name="payment-allocate"),
    path("donations/", views.donation_list, name="donation-list"),
    path("expenses/", views.expense_dashboard, name="expense-dashboard"),
    path("expenses/import/", views.expense_import_action, name="expense-import"),
    path(
        "expenses/transactions/<int:transaction_id>/categorize/",
        views.expense_categorize_action,
        name="expense-categorize",
    ),
    path("access/", views.access_dashboard, name="access-dashboard"),
    path("access/refresh-allowlist/", views.refresh_allowlist_action, name="refresh-allowlist"),
    path("reports/", views.reports_dashboard, name="reports-dashboard"),
    path("audit/", views.audit_timeline, name="audit-timeline"),
]
