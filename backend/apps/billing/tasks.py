from __future__ import annotations

from celery import shared_task

from apps.billing.services import dues_autopay_run, generate_due_scheduled_invoices, monthly_dues_close, reconcile_unposted_stripe_payments


@shared_task
def monthly_dues_close_task() -> int:
    return len(monthly_dues_close())


@shared_task
def scheduled_invoice_generation_task() -> int:
    return len(generate_due_scheduled_invoices())


@shared_task
def dues_autopay_run_task() -> int:
    return len(dues_autopay_run())


@shared_task
def stripe_reconciliation_sync_task() -> int:
    return reconcile_unposted_stripe_payments()
