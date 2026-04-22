from __future__ import annotations

from datetime import date, timedelta

import pytest

from apps.access.models import RFIDCredential
from apps.billing.models import Invoice, InvoiceLine, Payment
from apps.members.models import Client, Member


def create_member(name: str, email: str) -> Member:
    client = Client.objects.create(
        client_type=Client.ClientType.PERSON,
        display_name_text=name,
        email=email,
    )
    return Member.objects.create(
        client=client,
        status=Member.Status.ACTIVE,
        membership_class=Member.MembershipClass.FULL,
        voting_eligible=True,
        joined_at="2026-01-01",
    )


def create_invoice(member: Member, *, number: str, due_date: date, total_cents: int = 1000) -> Invoice:
    invoice = Invoice.objects.create(
        client=member.client,
        member=member,
        invoice_type=Invoice.InvoiceType.MEMBER_DUES,
        invoice_number=number,
        issue_date=due_date.replace(day=1),
        due_date=due_date,
        service_period_start=due_date.replace(day=1),
        service_period_end=due_date.replace(day=min(28, due_date.day)),
        status=Invoice.Status.ISSUED,
        total_cents=total_cents,
        external_processor=Invoice.ExternalProcessor.NONE,
    )
    InvoiceLine.objects.create(
        invoice=invoice,
        line_type=InvoiceLine.LineType.DUES,
        description=number,
        quantity=1,
        unit_price_cents=total_cents,
        line_total_cents=total_cents,
        amount_cents=total_cents,
    )
    return invoice


@pytest.mark.django_db
def test_staff_global_search_returns_cross_entity_results(staff_client):
    member = create_member("Global Member", "global-member@example.org")
    client_only = Client.objects.create(
        client_type=Client.ClientType.ORGANIZATION,
        display_name_text="Global Client",
        email="global-client@example.org",
    )
    invoice = create_invoice(member, number="INV-GLOBAL-001", due_date=date.today())
    payment = Payment.objects.create(
        client=member.client,
        member=member,
        received_at="2026-04-10T00:00:00Z",
        amount_cents=2500,
        currency="usd",
        payment_method=Payment.PaymentMethod.CASH,
        source_type=Payment.SourceType.DUES_PAYMENT,
        status=Payment.Status.SUCCEEDED,
        notes="global payment note",
    )
    credential = RFIDCredential.objects.create(member=member, uid="rfid-global-1", label="Global Fob")

    response = staff_client.get("/staff/search/", {"q": "global"})

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Global Search" in content
    assert "Global Member" in content
    assert "Global Client" in content
    assert invoice.invoice_number in content
    assert str(payment.pk) in content
    assert credential.uid in content
    assert f"/staff/members/{member.pk}/" in content
    assert f"/admin/members/client/{client_only.pk}/change/" in content
    assert "/api/invoices/" in content
    assert "/api/payments/" in content


@pytest.mark.django_db
def test_staff_member_list_supports_sort_order(staff_client):
    create_member("Alpha Sort", "alpha-sort@example.org")
    create_member("Zulu Sort", "zulu-sort@example.org")

    response = staff_client.get("/staff/members/", {"query": "Sort", "sort": "name_desc"})

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert content.index("Zulu Sort") < content.index("Alpha Sort")
    assert 'name="sort"' in content


@pytest.mark.django_db
def test_staff_billing_review_pages_support_date_filters_sort_and_escape_hatches(staff_client):
    member = create_member("Review Member", "review-member@example.org")
    old_invoice = create_invoice(member, number="INV-OLD-001", due_date=date.today() - timedelta(days=30))
    keep_invoice = create_invoice(member, number="INV-KEEP-001", due_date=date.today() - timedelta(days=5))
    old_payment = Payment.objects.create(
        client=member.client,
        member=member,
        received_at="2026-03-01T00:00:00Z",
        amount_cents=1000,
        currency="usd",
        payment_method=Payment.PaymentMethod.CASH,
        source_type=Payment.SourceType.DUES_PAYMENT,
        status=Payment.Status.SUCCEEDED,
    )
    keep_payment = Payment.objects.create(
        client=member.client,
        member=member,
        received_at="2026-04-10T00:00:00Z",
        amount_cents=2000,
        currency="usd",
        payment_method=Payment.PaymentMethod.CHECK,
        source_type=Payment.SourceType.DUES_PAYMENT,
        status=Payment.Status.SUCCEEDED,
    )

    invoice_response = staff_client.get(
        "/staff/billing/invoices/",
        {"query": "Review Member", "due_from": (date.today() - timedelta(days=10)).isoformat(), "sort": "due_asc"},
    )
    payment_response = staff_client.get(
        "/staff/billing/payments/",
        {"received_from": "2026-04-01", "sort": "amount_desc"},
    )

    assert invoice_response.status_code == 200
    invoice_content = invoice_response.content.decode("utf-8")
    assert keep_invoice.invoice_number in invoice_content
    assert old_invoice.invoice_number not in invoice_content
    assert f"/admin/billing/invoice/{keep_invoice.pk}/change/" in invoice_content
    assert f"/staff/members/{member.pk}/" in invoice_content
    assert "/api/invoices/" in invoice_content

    assert payment_response.status_code == 200
    payment_content = payment_response.content.decode("utf-8")
    assert str(keep_payment.pk) in payment_content
    assert f"/admin/billing/payment/{old_payment.pk}/change/" not in payment_content
    assert f"/admin/billing/payment/{keep_payment.pk}/change/" in payment_content
    assert f"/staff/members/{member.pk}/" in payment_content
    assert "/api/payments/" in payment_content
