from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.conf import settings
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.members.models import Client, ClientAlias, Member, MembershipTerm


@dataclass(slots=True)
class MemberBalance:
    credit_cents: int
    receivable_cents: int
    arrears_months: int
    next_due_date: date | None


def next_member_number() -> str:
    last_member = Member.objects.order_by("-id").first()
    next_number = (last_member.id if last_member else 0) + 1
    return f"M{next_number:05d}"


def compute_member_dues_amount(member: Member) -> int:
    return member.dues_amount_cents()


def client_snapshot(client: Client) -> dict:
    return {
        "client_type": client.client_type,
        "display_name": client.display_name,
        "legal_name": client.legal_name,
        "primary_email": client.email,
        "primary_phone": client.phone,
        "address_line1": client.address_line_1,
        "address_line2": client.address_line_2,
        "city": client.city,
        "state": client.state,
        "postal_code": client.postal_code,
        "country": client.country,
        "notes": client.notes,
        "is_active": client.is_active,
    }


def member_snapshot(member: Member) -> dict:
    return {
        "member_number": member.member_number,
        "membership_status": member.status,
        "membership_class": member.membership_class,
        "voting_eligible": member.voting_eligible,
        "door_access_enabled": member.door_access_enabled,
        "joined_on": member.joined_at.isoformat() if member.joined_at else None,
        "left_on": member.left_at.isoformat() if member.left_at else None,
        "autopay_enabled": member.autopay_enabled,
    }


def record_client_aliases(client: Client, before: dict, after: dict) -> None:
    alias_map = {
        "display_name": ClientAlias.AliasType.NAME,
        "primary_email": ClientAlias.AliasType.EMAIL,
        "primary_phone": ClientAlias.AliasType.PHONE,
    }
    for key, alias_type in alias_map.items():
        old_value = before.get(key)
        new_value = after.get(key)
        if old_value and old_value != new_value:
            ClientAlias.objects.get_or_create(
                client=client,
                alias_type=alias_type,
                value=old_value,
                valid_from=timezone.localdate(),
            )


def sync_membership_term(member: Member, *, reason: str = "", effective_from: date | None = None) -> MembershipTerm:
    effective_from = effective_from or member.joined_at or timezone.localdate()
    current = member.membership_terms.filter(effective_to__isnull=True).order_by("-effective_from", "-id").first()
    current_state = {
        "membership_class": member.membership_class,
        "monthly_dues_cents": member.dues_amount_cents(),
        "voting_eligible": member.voting_eligible,
        "door_access_enabled": member.door_access_enabled,
    }
    if current and {
        "membership_class": current.membership_class,
        "monthly_dues_cents": current.monthly_dues_cents,
        "voting_eligible": current.voting_eligible,
        "door_access_enabled": current.door_access_enabled,
    } == current_state:
        if reason and current.reason != reason:
            current.reason = reason
            current.save(update_fields=["reason"])
        return current
    if current and (current.effective_to is None or current.effective_to >= effective_from):
        current.effective_to = effective_from
        current.save(update_fields=["effective_to"])
    return MembershipTerm.objects.create(
        member=member,
        effective_from=effective_from,
        membership_class=member.membership_class,
        monthly_dues_cents=member.dues_amount_cents(),
        voting_eligible=member.voting_eligible,
        door_access_enabled=member.door_access_enabled,
        reason=reason,
    )


def get_member_balance(member: Member, as_of: date | None = None) -> MemberBalance:
    from apps.billing.models import Invoice, Payment

    as_of = as_of or timezone.localdate()
    invoices = (
        Invoice.objects.filter(member=member)
        .exclude(status=Invoice.Status.VOID)
        .filter(issue_date__lte=as_of)
        .annotate(
            paid_cents=Coalesce(
                Sum(
                    "allocations__allocated_cents",
                    filter=Q(
                        allocations__payment__status=Payment.Status.SUCCEEDED,
                        allocations__payment__received_at__date__lte=as_of,
                    ),
                ),
                0,
            )
        )
        .order_by("due_date", "issue_date", "id")
    )
    receivable_cents = 0
    arrears_months = 0
    next_due_date = None
    for invoice in invoices:
        remaining = max(invoice.total_cents - invoice.paid_cents, 0)
        receivable_cents += remaining
        if remaining > 0 and next_due_date is None:
            next_due_date = invoice.due_date
        if remaining > 0 and invoice.due_date <= as_of:
            arrears_months += 1

    total_payments = (
        Payment.objects.filter(member=member, status=Payment.Status.SUCCEEDED, received_at__date__lte=as_of)
        .aggregate(total=Coalesce(Sum("amount_cents"), 0))
        .get("total", 0)
    )
    allocated_cents = (
        Payment.objects.filter(member=member, status=Payment.Status.SUCCEEDED, received_at__date__lte=as_of)
        .aggregate(total=Coalesce(Sum("allocations__allocated_cents"), 0))
        .get("total", 0)
    )
    credit_cents = max(total_payments - allocated_cents, 0)
    return MemberBalance(
        credit_cents=credit_cents,
        receivable_cents=receivable_cents,
        arrears_months=arrears_months,
        next_due_date=next_due_date,
    )


def update_member_status_from_balance(member: Member, as_of: date | None = None) -> MemberBalance:
    as_of = as_of or timezone.localdate()
    balance = get_member_balance(member, as_of=as_of)
    if member.status == Member.Status.LEFT:
        return balance

    if balance.arrears_months >= settings.ARREARS_SUSPENSION_MONTHS and as_of.day >= settings.DUES_DUE_DAY:
        new_status = Member.Status.SUSPENDED
    elif balance.receivable_cents > 0:
        new_status = Member.Status.PAST_DUE
    else:
        new_status = Member.Status.ACTIVE

    if member.status != new_status:
        old_status = member.status
        member.status = new_status
        member.save(update_fields=["status", "updated_at"])
        from apps.audit.services import log_audit_event

        log_audit_event(
            actor="system",
            actor_type="system",
            entity_type="Member",
            entity_id=str(member.pk),
            action="member.status.changed",
            before_json={"status": old_status},
            after_json={"status": new_status},
            changes={"old_status": old_status, "new_status": new_status},
            message=f"Status changed for member {member.pk}",
        )
    return balance
