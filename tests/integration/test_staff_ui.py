from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client as DjangoClient

from apps.access.models import AccessAllowlistSnapshot, AccessEvent, RFIDCredential
from apps.audit.services import log_audit_event
from apps.billing.models import Invoice, InvoiceLine, InvoiceSchedule, Payment, ProcessorChoices, WebhookEvent
from apps.donations.models import Donation
from apps.expenses.models import BankImportSource, Expense, ExpenseImportBatch, ImportedBankTransaction
from apps.members.models import Client, Member


def create_member(
    name: str,
    email: str,
    *,
    status: str = Member.Status.ACTIVE,
    membership_class: str = Member.MembershipClass.FULL,
    autopay_enabled: bool = False,
    door_access_enabled: bool = False,
) -> Member:
    client = Client.objects.create(
        client_type=Client.ClientType.PERSON,
        display_name_text=name,
        email=email,
    )
    return Member.objects.create(
        client=client,
        status=status,
        membership_class=membership_class,
        voting_eligible=membership_class == Member.MembershipClass.FULL,
        joined_at="2026-01-01",
        autopay_enabled=autopay_enabled,
        door_access_enabled=door_access_enabled,
    )


def create_invoice(
    member: Member,
    *,
    number: str,
    total_cents: int = 5000,
    due_date: date | None = None,
    status: str = Invoice.Status.ISSUED,
) -> Invoice:
    due_date = due_date or date.today()
    invoice = Invoice.objects.create(
        client=member.client,
        member=member,
        invoice_type=Invoice.InvoiceType.MEMBER_DUES,
        invoice_number=number,
        issue_date=due_date.replace(day=1),
        due_date=due_date,
        service_period_start=due_date.replace(day=1),
        service_period_end=(due_date.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1),
        status=status,
        currency="usd",
        total_cents=total_cents,
        description=number,
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
def test_staff_pages_require_staff_user():
    anonymous_response = DjangoClient().get("/staff/")

    user = get_user_model().objects.create_user(
        username="member-user",
        email="member@example.org",
        password="test-password",
        is_staff=False,
    )
    non_staff_client = DjangoClient()
    non_staff_client.force_login(user)
    non_staff_response = non_staff_client.get("/staff/")

    assert anonymous_response.status_code == 302
    assert "/admin/login/" in anonymous_response["Location"]
    assert non_staff_response.status_code == 302
    assert "/admin/login/" in non_staff_response["Location"]


@pytest.mark.django_db
def test_staff_home_lists_navigation_and_operational_counts(staff_client):
    create_member("Past Due Person", "past-due@example.org", status=Member.Status.PAST_DUE)
    create_member("Suspended Person", "suspended@example.org", status=Member.Status.SUSPENDED)
    create_member("Autopay Person", "autopay@example.org", autopay_enabled=True)
    WebhookEvent.objects.create(
        processor=ProcessorChoices.STRIPE,
        event_id="invalid-evt-1",
        payload_json={"bad": True},
        signature_valid=False,
    )
    snapshot = AccessAllowlistSnapshot.objects.create(etag="etag-1", payload_json={"members": []}, signature="sig-1")
    member = create_member("Expense Person", "expense@example.org")
    AccessEvent.objects.create(member=member, credential_uid="cred-home-1", result="granted")
    source = BankImportSource.objects.create(name="Checking", parser_key="generic_csv")
    batch = ExpenseImportBatch.objects.create(source=source)
    ImportedBankTransaction.objects.create(
        source=source,
        import_batch=batch,
        posted_on=date(2026, 4, 8),
        description_raw="Internet Provider",
        amount_cents=800,
        direction=ImportedBankTransaction.Direction.DEBIT,
        currency="usd",
        external_hash="hash-home-1",
    )

    response = staff_client.get("/staff/")

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Members" in content
    assert "Billing" in content
    assert "Donations" in content
    assert "Expenses" in content
    assert "Access" in content
    assert "Reports" in content
    assert "Audit" in content
    assert "Past Due Members" in content
    assert "Suspended Members" in content
    assert "Invalid Webhooks" in content
    assert snapshot.etag in content


@pytest.mark.django_db
def test_staff_member_search_and_workspace_render_member_context(staff_client):
    target = create_member("Pat Search", "pat-search@example.org", status=Member.Status.PAST_DUE, door_access_enabled=True)
    other = create_member("Other Person", "other@example.org", status=Member.Status.ACTIVE)
    create_invoice(target, number="INV-SEARCH-001", due_date=date.today() - timedelta(days=10))
    RFIDCredential.objects.create(member=target, uid="rfid-search-1", label="Blue Fob")

    list_response = staff_client.get("/staff/members/", {"status": Member.Status.PAST_DUE, "query": "Pat"})
    detail_response = staff_client.get(f"/staff/members/{target.pk}/")

    assert list_response.status_code == 200
    list_content = list_response.content.decode("utf-8")
    assert "Pat Search" in list_content
    assert "Other Person" not in list_content
    assert f"/staff/members/{target.pk}/" in list_content

    assert detail_response.status_code == 200
    detail_content = detail_response.content.decode("utf-8")
    assert "Pat Search" in detail_content
    assert "INV-SEARCH-001" in detail_content
    assert "rfid-search-1" in detail_content
    assert "Record Manual Payment" in detail_content
    assert "Create One-Off Invoice" in detail_content
    assert f"/admin/members/member/{target.pk}/change/" in detail_content
    assert f"/admin/members/member/{other.pk}/change/" not in detail_content


@pytest.mark.django_db
def test_staff_member_workspace_actions_record_payment_create_invoice_and_manage_access(staff_client):
    member = create_member("Action Member", "action-member@example.org", status=Member.Status.PAST_DUE)
    create_invoice(member, number="INV-ACTION-001", due_date=date.today() - timedelta(days=15))

    payment_response = staff_client.post(
        f"/staff/members/{member.pk}/manual-payment/",
        data={
            "amount_cents": 5000,
            "payment_method": Payment.PaymentMethod.CASH,
            "source_type": Payment.SourceType.DUES_PAYMENT,
            "note": "front desk cash",
        },
        follow=True,
    )
    invoice_response = staff_client.post(
        f"/staff/members/{member.pk}/one-off-invoices/",
        data={"invoice_number": "INV-ACTION-002", "description": "Locker fee", "amount_cents": 1200},
        follow=True,
    )
    credential_response = staff_client.post(
        f"/staff/members/{member.pk}/rfid/add/",
        data={"uid": "rfid-action-1", "label": "Silver Tag"},
        follow=True,
    )
    access_response = staff_client.post(
        f"/staff/members/{member.pk}/door-access/",
        data={"door_access_enabled": "on"},
        follow=True,
    )

    member.refresh_from_db()

    assert payment_response.status_code == 200
    assert invoice_response.status_code == 200
    assert credential_response.status_code == 200
    assert access_response.status_code == 200
    assert Payment.objects.filter(member=member, amount_cents=5000, payment_method=Payment.PaymentMethod.CASH).exists()
    assert Invoice.objects.filter(member=member, invoice_number="INV-ACTION-002").exists()
    assert RFIDCredential.objects.filter(member=member, uid="rfid-action-1", is_active=True).exists()
    assert member.door_access_enabled is True


@pytest.mark.django_db
def test_staff_billing_console_and_review_pages_support_actions(staff_client):
    active_member = create_member("Billing Member", "billing@example.org")
    draft_invoice = create_invoice(
        active_member,
        number="INV-BILLING-DRAFT",
        due_date=date.today(),
        total_cents=2500,
        status=Invoice.Status.DRAFT,
    )
    open_invoice = create_invoice(
        active_member,
        number="INV-BILLING-OPEN",
        due_date=date.today() - timedelta(days=5),
        total_cents=3000,
    )
    payment = Payment.objects.create(
        client=active_member.client,
        member=active_member,
        amount_cents=3000,
        currency="usd",
        payment_method=Payment.PaymentMethod.CASH,
        source_type=Payment.SourceType.DUES_PAYMENT,
        status=Payment.Status.SUCCEEDED,
    )
    InvoiceSchedule.objects.create(
        client=active_member.client,
        member=active_member,
        invoice_type=Invoice.InvoiceType.RECURRING_AD_HOC,
        description="Quarterly locker rental",
        frequency=InvoiceSchedule.Frequency.MONTHLY,
        generation_day=1,
        due_day=15,
        amount_cents=1500,
        active=True,
    )

    dashboard = staff_client.get("/staff/billing/")
    close_response = staff_client.post("/staff/billing/run/", data={"action": "monthly_dues_close"}, follow=True)
    issue_response = staff_client.post(f"/staff/billing/invoices/{draft_invoice.pk}/issue/", follow=True)
    allocate_response = staff_client.post(
        f"/staff/billing/payments/{payment.pk}/allocate/",
        data={"invoice_ids": [open_invoice.pk]},
        follow=True,
    )

    draft_invoice.refresh_from_db()

    assert dashboard.status_code == 200
    assert "Run Monthly Dues Close" in dashboard.content.decode("utf-8")
    assert close_response.status_code == 200
    assert Invoice.objects.filter(invoice_number=f"DUES-{date.today():%Y%m}-{active_member.pk:04d}").exists()
    assert issue_response.status_code == 200
    assert draft_invoice.status == Invoice.Status.ISSUED
    assert allocate_response.status_code == 200
    assert payment.allocations.filter(invoice=open_invoice).exists()


@pytest.mark.django_db
def test_staff_donations_page_lists_recent_donations(staff_client):
    Donation.objects.create(
        external_charge_id="every-staff-1",
        donor_name="Donor Person",
        donor_email="donor@example.org",
        amount_cents=1500,
        net_amount_cents=1300,
        currency="usd",
        frequency="one_time",
        donation_date="2026-04-04T00:00:00Z",
        payment_method="card",
        designation="Wood Shop",
        raw_payload={"chargeId": "every-staff-1"},
    )

    response = staff_client.get("/staff/donations/")

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Donor Person" in content
    assert "Wood Shop" in content
    assert "every-staff-1" in content


@pytest.mark.django_db
def test_staff_expenses_page_imports_and_categorizes_transactions(staff_client):
    import_response = staff_client.post(
        "/staff/expenses/import/",
        data={
            "source_name": "Checking",
            "parser_key": "generic_csv",
            "csv_content": "posted_on,description,amount_cents,direction,currency\n2026-04-08,Internet Provider,800,DEBIT,usd\n",
        },
        follow=True,
    )
    transaction = ImportedBankTransaction.objects.get(description_raw="Internet Provider")
    categorize_response = staff_client.post(
        f"/staff/expenses/transactions/{transaction.pk}/categorize/",
        data={"category_code": "INTERNET", "category_name": "Internet", "reconciled": "on"},
        follow=True,
    )

    transaction.refresh_from_db()

    assert import_response.status_code == 200
    assert categorize_response.status_code == 200
    assert transaction.expense is not None
    assert transaction.expense.category.code == "INTERNET"
    assert transaction.is_reconciled is True


@pytest.mark.django_db
def test_staff_access_page_shows_events_and_can_refresh_allowlist(staff_client):
    member = create_member("Access Member", "access-member@example.org", status=Member.Status.ACTIVE, door_access_enabled=True)
    RFIDCredential.objects.create(member=member, uid="rfid-access-1", label="Front Door")
    AccessEvent.objects.create(member=member, credential_uid="rfid-access-1", result="granted")

    page_response = staff_client.get("/staff/access/")
    refresh_response = staff_client.post("/staff/access/refresh-allowlist/", follow=True)

    assert page_response.status_code == 200
    assert "rfid-access-1" in page_response.content.decode("utf-8")
    assert refresh_response.status_code == 200
    assert AccessAllowlistSnapshot.objects.exists()


@pytest.mark.django_db
def test_staff_reports_page_renders_report_sections_and_export_links(staff_client):
    member = create_member("Reports Member", "reports-member@example.org")
    invoice = create_invoice(member, number="INV-REPORTS-001", due_date=date(2026, 4, 15), total_cents=5000)
    payment = Payment.objects.create(
        client=member.client,
        member=member,
        amount_cents=5000,
        currency="usd",
        payment_method=Payment.PaymentMethod.CASH,
        source_type=Payment.SourceType.DUES_PAYMENT,
        status=Payment.Status.SUCCEEDED,
        received_at="2026-04-10T00:00:00Z",
    )
    invoice.allocations.create(payment=payment, allocated_cents=5000)
    Donation.objects.create(
        external_charge_id="every-reports-1",
        donor_name="Report Donor",
        amount_cents=2500,
        currency="usd",
        donation_date="2026-04-05T00:00:00Z",
        raw_payload={"chargeId": "every-reports-1"},
    )
    Expense.objects.create(description="Internet", booked_on="2026-04-08", amount_cents=800)

    response = staff_client.get("/staff/reports/", {"from": "2026-04-01", "to": "2026-04-30"})

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Financial Report" in content
    assert "Member Balances" in content
    assert "A/R Aging" in content
    assert "/api/exports/financial.csv?from=2026-04-01&to=2026-04-30" in content
    assert "/api/exports/member-balances.csv" in content
    assert "Reports Member" in content


@pytest.mark.django_db
def test_staff_audit_page_filters_entries(staff_client):
    log_audit_event(
        actor="api",
        actor_type="api",
        entity_type="Member",
        entity_id="1",
        action="member.updated",
        message="Member updated",
    )
    log_audit_event(
        actor="system",
        actor_type="system",
        entity_type="Invoice",
        entity_id="2",
        action="invoice.issued",
        message="Invoice issued",
    )

    response = staff_client.get("/staff/audit/", {"entity_type": "Member", "action": "member.updated"})

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "member.updated" in content
    assert "invoice.issued" not in content


@pytest.mark.django_db
def test_staff_home_and_review_pages_expose_operational_queues(staff_client):
    active_member = create_member("Active Queue", "active-queue@example.org", status=Member.Status.ACTIVE)
    past_due_member = create_member(
        "Past Due Queue",
        "past-due-queue@example.org",
        status=Member.Status.PAST_DUE,
        autopay_enabled=True,
        door_access_enabled=True,
    )
    create_invoice(
        active_member,
        number="INV-QUEUE-CURRENT",
        due_date=date.today() + timedelta(days=7),
    )
    overdue_invoice = create_invoice(
        past_due_member,
        number="INV-QUEUE-OVERDUE",
        due_date=date.today() - timedelta(days=7),
    )
    stripe_payment = Payment.objects.create(
        client=past_due_member.client,
        member=past_due_member,
        amount_cents=3500,
        currency="usd",
        payment_method=Payment.PaymentMethod.STRIPE_CARD,
        source_type=Payment.SourceType.DUES_PAYMENT,
        processor=ProcessorChoices.STRIPE,
        processor_payment_id="pi-queue-1",
        status=Payment.Status.SUCCEEDED,
    )
    Payment.objects.create(
        client=active_member.client,
        member=active_member,
        amount_cents=2000,
        currency="usd",
        payment_method=Payment.PaymentMethod.CASH,
        source_type=Payment.SourceType.DUES_PAYMENT,
        status=Payment.Status.SUCCEEDED,
    )

    home_response = staff_client.get("/staff/")
    past_due_response = staff_client.get("/staff/members/", {"queue": "past_due"})
    door_access_response = staff_client.get("/staff/members/", {"queue": "door_access"})
    overdue_response = staff_client.get("/staff/billing/invoices/", {"queue": "overdue"})
    stripe_queue_response = staff_client.get("/staff/billing/payments/", {"queue": "unreconciled_stripe"})

    assert home_response.status_code == 200
    home_content = home_response.content.decode("utf-8")
    assert "/staff/members/?queue=active" in home_content
    assert "/staff/members/?queue=past_due" in home_content
    assert "/staff/members/?queue=suspended" in home_content
    assert "/staff/members/?queue=autopay" in home_content
    assert "/staff/members/?queue=door_access" in home_content
    assert "/staff/billing/invoices/?queue=overdue" in home_content
    assert "/staff/billing/payments/?queue=unreconciled_stripe" in home_content
    assert "/staff/expenses/?queue=uncategorized" in home_content
    assert "/staff/expenses/?queue=needs_reconciliation" in home_content

    past_due_content = past_due_response.content.decode("utf-8")
    assert "Past Due Queue" in past_due_content
    assert "Active Queue" not in past_due_content

    door_access_content = door_access_response.content.decode("utf-8")
    assert "Past Due Queue" in door_access_content
    assert "Active Queue" not in door_access_content

    overdue_content = overdue_response.content.decode("utf-8")
    assert overdue_invoice.invoice_number in overdue_content
    assert "INV-QUEUE-CURRENT" not in overdue_content

    stripe_queue_content = stripe_queue_response.content.decode("utf-8")
    assert str(stripe_payment.pk) in stripe_queue_content
    assert "Allocate Payment" in stripe_queue_content


@pytest.mark.django_db
def test_staff_invoice_review_supports_bulk_issue_and_void(staff_client):
    member = create_member("Bulk Invoice Member", "bulk-invoice@example.org")
    draft_one = create_invoice(
        member,
        number="INV-BULK-DRAFT-001",
        due_date=date.today(),
        total_cents=1400,
        status=Invoice.Status.DRAFT,
    )
    draft_two = create_invoice(
        member,
        number="INV-BULK-DRAFT-002",
        due_date=date.today() + timedelta(days=1),
        total_cents=1600,
        status=Invoice.Status.DRAFT,
    )
    issued_one = create_invoice(
        member,
        number="INV-BULK-ISSUED-001",
        due_date=date.today() + timedelta(days=2),
        total_cents=1800,
        status=Invoice.Status.ISSUED,
    )

    issue_response = staff_client.post(
        "/staff/billing/invoices/bulk-action/",
        data={"action": "issue", "invoice_ids": [draft_one.pk, draft_two.pk]},
        follow=True,
    )
    void_response = staff_client.post(
        "/staff/billing/invoices/bulk-action/",
        data={"action": "void", "invoice_ids": [issued_one.pk]},
        follow=True,
    )

    draft_one.refresh_from_db()
    draft_two.refresh_from_db()
    issued_one.refresh_from_db()

    assert issue_response.status_code == 200
    assert void_response.status_code == 200
    assert draft_one.status == Invoice.Status.ISSUED
    assert draft_two.status == Invoice.Status.ISSUED
    assert issued_one.status == Invoice.Status.VOID


@pytest.mark.django_db
def test_staff_support_pages_expose_escape_hatches_and_expense_queues(staff_client):
    member = create_member("Support Member", "support-member@example.org", door_access_enabled=True)
    snapshot = AccessAllowlistSnapshot.objects.create(
        etag="etag-support-1",
        payload_json={"members": [{"member_id": member.pk}]},
        signature="sig-support-1",
    )
    RFIDCredential.objects.create(member=member, uid="rfid-support-1", label="Support Fob")
    AccessEvent.objects.create(member=member, credential_uid="rfid-support-1", result="granted")
    Donation.objects.create(
        external_charge_id="every-support-1",
        donor_name="Support Donor",
        amount_cents=2200,
        currency="usd",
        donation_date="2026-04-04T00:00:00Z",
        raw_payload={"chargeId": "every-support-1"},
    )
    source = BankImportSource.objects.create(name="Operations", parser_key="generic_csv")
    batch = ExpenseImportBatch.objects.create(source=source)
    uncategorized = ImportedBankTransaction.objects.create(
        source=source,
        import_batch=batch,
        posted_on=date(2026, 4, 7),
        description_raw="Raw Utilities",
        amount_cents=800,
        direction=ImportedBankTransaction.Direction.DEBIT,
        currency="usd",
        external_hash="support-expense-uncategorized",
    )
    reconciled_expense = Expense.objects.create(
        description="Reconciled Internet",
        booked_on=date(2026, 4, 6),
        amount_cents=900,
        review_status=Expense.ReviewStatus.RECONCILED,
    )
    needs_reconciliation_expense = Expense.objects.create(
        description="Pending Reconciliation",
        booked_on=date(2026, 4, 5),
        amount_cents=1100,
        review_status=Expense.ReviewStatus.CATEGORIZED,
    )
    ImportedBankTransaction.objects.create(
        source=source,
        import_batch=batch,
        posted_on=date(2026, 4, 6),
        description_raw="Reconciled Internet",
        amount_cents=900,
        direction=ImportedBankTransaction.Direction.DEBIT,
        currency="usd",
        external_hash="support-expense-reconciled",
        expense=reconciled_expense,
        is_reconciled=True,
    )
    ImportedBankTransaction.objects.create(
        source=source,
        import_batch=batch,
        posted_on=date(2026, 4, 5),
        description_raw="Pending Reconciliation",
        amount_cents=1100,
        direction=ImportedBankTransaction.Direction.DEBIT,
        currency="usd",
        external_hash="support-expense-pending",
        expense=needs_reconciliation_expense,
        is_reconciled=False,
    )

    donation_response = staff_client.get("/staff/donations/")
    access_response = staff_client.get("/staff/access/")
    expense_response = staff_client.get("/staff/expenses/", {"queue": "needs_reconciliation"})

    assert donation_response.status_code == 200
    donation_content = donation_response.content.decode("utf-8")
    assert "/api/donations" in donation_content
    assert "/admin/donations/donation/" in donation_content
    assert "/staff/audit/?entity_type=Donation" in donation_content

    assert access_response.status_code == 200
    access_content = access_response.content.decode("utf-8")
    assert snapshot.etag in access_content
    assert "/api/access/allowlist/" in access_content
    assert "/api/access/events/" in access_content
    assert f"/api/access/members/{member.pk}/entitlement" in access_content
    assert "/admin/access/rfidcredential/" in access_content
    assert "/admin/access/accessallowlistsnapshot/" in access_content
    assert "/admin/access/accessevent/" in access_content
    assert f"/staff/members/{member.pk}/" in access_content

    assert expense_response.status_code == 200
    expense_content = expense_response.content.decode("utf-8")
    assert "/api/expenses/import-batches" in expense_content
    assert "/admin/expenses/importedbanktransaction/" in expense_content
    assert "/admin/expenses/expensecategorizationrule/" in expense_content
    assert "/staff/expenses/?queue=uncategorized" in expense_content
    assert "/staff/expenses/?queue=needs_reconciliation" in expense_content
    assert "Pending Reconciliation" in expense_content
    assert uncategorized.description_raw not in expense_content
    assert reconciled_expense.description not in expense_content


@pytest.mark.django_db
def test_staff_audit_page_supports_entity_id_date_range_and_entity_links(staff_client):
    member = create_member("Audit Member", "audit-member@example.org")
    included = log_audit_event(
        actor="api",
        actor_type="api",
        entity_type="Member",
        entity_id=str(member.pk),
        action="member.updated",
        before_json={"status": "ACTIVE"},
        after_json={"status": "PAST_DUE"},
        message="Status updated",
    )
    included.occurred_at = "2026-04-10T00:00:00Z"
    included.save(update_fields=["occurred_at"])
    excluded = log_audit_event(
        actor="system",
        actor_type="system",
        entity_type="Member",
        entity_id=str(member.pk),
        action="member.updated",
        message="Old status update",
    )
    excluded.occurred_at = "2026-03-10T00:00:00Z"
    excluded.save(update_fields=["occurred_at"])
    log_audit_event(
        actor="system",
        actor_type="system",
        entity_type="Invoice",
        entity_id="999",
        action="invoice.issued",
        message="Other entity",
    )

    response = staff_client.get(
        "/staff/audit/",
        {
            "entity_type": "Member",
            "entity_id": str(member.pk),
            "occurred_from": "2026-04-01",
            "occurred_to": "2026-04-30",
        },
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Status updated" in content
    assert "Old status update" not in content
    assert "Other entity" not in content
    assert f"/admin/members/member/{member.pk}/change/" in content
    assert "status" in content


@pytest.mark.django_db
def test_payment_return_pages_render():
    success_response = DjangoClient().get("/payments/success")
    cancel_response = DjangoClient().get("/payments/cancel")

    assert success_response.status_code == 200
    assert cancel_response.status_code == 200
    assert "Payment Complete" in success_response.content.decode("utf-8")
    assert "Payment Cancelled" in cancel_response.content.decode("utf-8")
