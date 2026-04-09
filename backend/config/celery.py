from __future__ import annotations

import os

from celery import Celery


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "monthly-dues-close": {
        "task": "apps.billing.tasks.monthly_dues_close_task",
        "schedule": 3600.0,
    },
    "scheduled-invoice-generation": {
        "task": "apps.billing.tasks.scheduled_invoice_generation_task",
        "schedule": 3600.0,
    },
    "enforcement-run": {
        "task": "apps.members.tasks.enforcement_run_task",
        "schedule": 3600.0,
    },
    "refresh-allowlist": {
        "task": "apps.access.tasks.refresh_allowlist_task",
        "schedule": 300.0,
    },
}
