from __future__ import annotations


def test_celery_app_is_configured():
    from config.celery import app

    assert app.main == "config"
    assert "scheduled-invoice-generation" in app.conf.beat_schedule
    assert "dues-autopay-run" in app.conf.beat_schedule
    assert "stripe-reconciliation-sync" in app.conf.beat_schedule
