from __future__ import annotations

from datetime import date

import pytest

from apps.donations.models import Donation
from apps.donations.services import process_everyorg_webhook
from apps.ledger.models import JournalEntry, JournalLine
from apps.ledger.services import create_balanced_entry, post_payment
from apps.members.models import Client, Member, MembershipTerm
from apps.members.services import sync_membership_term, update_member_status_from_balance


def create_member(*, status: str = Member.Status.ACTIVE) -> Member:
    client = Client.objects.create(
        client_type=Client.ClientType.PERSON,
        display_name_text=f"Domain Member {Client.objects.count() + 1}",
        email=f"domain-{Client.objects.count() + 1}@example.org",
    )
    return Member.objects.create(
        client=client,
        status=status,
        membership_class=Member.MembershipClass.FULL,
        voting_eligible=True,
        joined_at="2026-01-01",
    )


@pytest.mark.django_db
def test_process_everyorg_webhook_uses_now_when_date_missing():
    donation = process_everyorg_webhook(
        {
            "chargeId": "every-now-1",
            "amount": 2500,
            "currency": "usd",
            "designation": "General Fund",
        }
    )

    stored = Donation.objects.get(pk=donation.pk)
    assert stored.donor_name == ""
    assert stored.net_amount_cents is None
    assert stored.donation_date is not None


@pytest.mark.django_db
def test_sync_membership_term_reuses_current_term_and_left_status_stays_left():
    member = create_member(status=Member.Status.LEFT)
    original = sync_membership_term(member, reason="Initial")

    same_term = sync_membership_term(member, reason="Clarified reason")
    member.status = Member.Status.LEFT
    member.save(update_fields=["status", "updated_at"])
    balance = update_member_status_from_balance(member, as_of=date(2026, 4, 15))

    assert same_term.pk == original.pk
    original.refresh_from_db()
    assert original.reason == "Clarified reason"
    assert MembershipTerm.objects.filter(member=member).count() == 1
    assert member.status == Member.Status.LEFT
    assert balance.receivable_cents == 0


@pytest.mark.django_db
def test_create_balanced_entry_is_idempotent_and_rejects_unbalanced():
    entry = create_balanced_entry(
        occurred_on=date(2026, 4, 1),
        description="Balanced",
        reference="balanced-1",
        source_type="test",
        source_id="1",
        lines=[
            ("1120", JournalLine.EntryType.DEBIT, 1000, "cash"),
            ("4100", JournalLine.EntryType.CREDIT, 1000, "income"),
        ],
    )
    same_entry = create_balanced_entry(
        occurred_on=date(2026, 4, 1),
        description="Balanced",
        reference="balanced-1",
        source_type="test",
        source_id="1",
        lines=[
            ("1120", JournalLine.EntryType.DEBIT, 1000, "cash"),
            ("4100", JournalLine.EntryType.CREDIT, 1000, "income"),
        ],
    )

    assert same_entry.pk == entry.pk
    assert JournalEntry.objects.filter(source_type="test", source_id="1").count() == 1

    with pytest.raises(ValueError, match="not balanced"):
        create_balanced_entry(
            occurred_on=date(2026, 4, 1),
            description="Broken",
            reference="broken-1",
            source_type="test",
            source_id="2",
            lines=[
                ("1120", JournalLine.EntryType.DEBIT, 1000, "cash"),
                ("4100", JournalLine.EntryType.CREDIT, 900, "income"),
            ],
        )


@pytest.mark.django_db
def test_post_payment_returns_none_for_non_succeeded_payment():
    member = create_member()
    payment = member.payments.create(
        client=member.client,
        amount_cents=1000,
        payment_method="CASH",
        source_type="OTHER_INCOME",
        status="FAILED",
    )

    assert post_payment(payment) is None
