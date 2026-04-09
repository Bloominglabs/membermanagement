from __future__ import annotations

from dataclasses import asdict

from rest_framework import serializers

from apps.access.models import AccessEvent
from apps.audit.services import log_audit_event
from apps.billing.models import Allocation, Invoice, InvoiceLine, InvoiceSchedule, Payment
from apps.billing.services import calculate_due_date
from apps.donations.models import Donation
from apps.expenses.models import Expense, ExpenseCategorizationRule, ExpenseCategory, ImportedBankTransaction
from apps.members.models import Client, Member
from apps.members.services import (
    MemberBalance,
    client_snapshot,
    member_snapshot,
    next_member_number,
    record_client_aliases,
    sync_membership_term,
)


class ClientSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(source="display_name_text", allow_blank=True, required=False)
    primary_email = serializers.EmailField(source="email")
    primary_phone = serializers.CharField(source="phone", allow_blank=True, required=False)
    address_line1 = serializers.CharField(source="address_line_1", allow_blank=True, required=False)
    address_line2 = serializers.CharField(source="address_line_2", allow_blank=True, required=False)

    class Meta:
        model = Client
        fields = [
            "id",
            "client_type",
            "display_name",
            "legal_name",
            "primary_email",
            "primary_phone",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "postal_code",
            "country",
            "notes",
            "is_active",
            "metadata",
        ]

    def create(self, validated_data: dict) -> Client:
        client = Client.objects.create(**validated_data)
        log_audit_event(
            actor="api",
            actor_type="api",
            entity_type="Client",
            entity_id=str(client.pk),
            action="client.created",
            after_json=client_snapshot(client),
            message=f"Client {client.pk} created",
        )
        return client

    def update(self, instance: Client, validated_data: dict) -> Client:
        before = client_snapshot(instance)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        after = client_snapshot(instance)
        record_client_aliases(instance, before, after)
        log_audit_event(
            actor="api",
            actor_type="api",
            entity_type="Client",
            entity_id=str(instance.pk),
            action="client.updated",
            before_json=before,
            after_json=after,
            message=f"Client {instance.pk} updated",
        )
        return instance


class MemberSerializer(serializers.ModelSerializer):
    client = ClientSerializer()
    membership_status = serializers.ChoiceField(source="status", choices=Member.Status.choices)
    joined_on = serializers.DateField(source="joined_at")
    left_on = serializers.DateField(source="left_at", allow_null=True, required=False)
    reason = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Member
        fields = [
            "id",
            "client",
            "member_number",
            "membership_status",
            "membership_class",
            "voting_eligible",
            "door_access_enabled",
            "joined_on",
            "left_on",
            "dues_override_cents",
            "autopay_enabled",
            "stripe_customer_id",
            "default_payment_method_id",
            "notes",
            "metadata",
            "reason",
        ]

    def create(self, validated_data: dict) -> Member:
        client_data = validated_data.pop("client")
        reason = validated_data.pop("reason", "")
        client = ClientSerializer().create(client_data)
        if not validated_data.get("member_number"):
            validated_data["member_number"] = next_member_number()
        member = Member.objects.create(client=client, **validated_data)
        sync_membership_term(member, reason=reason or "Initial membership state", effective_from=member.joined_at)
        log_audit_event(
            actor="api",
            actor_type="api",
            entity_type="Member",
            entity_id=str(member.pk),
            action="member.created",
            after_json=member_snapshot(member),
            reason=reason,
            message=f"Member {member.pk} created",
        )
        return member

    def update(self, instance: Member, validated_data: dict) -> Member:
        client_data = validated_data.pop("client", None)
        reason = validated_data.pop("reason", "")
        if client_data:
            ClientSerializer().update(instance.client, client_data)
        before = member_snapshot(instance)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        sync_membership_term(instance, reason=reason or "Membership updated", effective_from=instance.joined_at)
        log_audit_event(
            actor="api",
            actor_type="api",
            entity_type="Member",
            entity_id=str(instance.pk),
            action="member.updated",
            before_json=before,
            after_json=member_snapshot(instance),
            reason=reason,
            message=f"Member {instance.pk} updated",
        )
        return instance


class MemberBalanceSerializer(serializers.Serializer):
    credit_cents = serializers.IntegerField()
    receivable_cents = serializers.IntegerField()
    arrears_months = serializers.IntegerField()
    next_due_date = serializers.DateField(allow_null=True)

    @classmethod
    def from_balance(cls, balance: MemberBalance) -> dict:
        return cls(asdict(balance)).data


class ManualPaymentSerializer(serializers.Serializer):
    amount_cents = serializers.IntegerField(min_value=1)
    source_type = serializers.ChoiceField(
        choices=[
            "DUES_PAYMENT",
            "PREPAYMENT_TOPUP",
            "ARREARS_CATCHUP",
            "DONATION",
            "OTHER_INCOME",
        ],
        default="OTHER_INCOME",
    )
    note = serializers.CharField(required=False, allow_blank=True)


class StripeCheckoutRequestSerializer(serializers.Serializer):
    member_id = serializers.IntegerField()
    mode = serializers.ChoiceField(choices=["top_up", "pay_balance"])
    amount_cents = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    success_url = serializers.URLField(required=False)
    cancel_url = serializers.URLField(required=False)


class StripeSetupIntentRequestSerializer(serializers.Serializer):
    member_id = serializers.IntegerField()


class InvoiceLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLine
        fields = [
            "id",
            "line_type",
            "description",
            "quantity",
            "unit_price_cents",
            "line_total_cents",
            "amount_cents",
            "service_period_start",
            "service_period_end",
            "income_category",
        ]
        read_only_fields = ["id", "amount_cents"]


class InvoiceSerializer(serializers.ModelSerializer):
    lines = InvoiceLineSerializer(many=True, required=False)
    due_date = serializers.DateField(required=False)
    due_day = serializers.IntegerField(write_only=True, required=False)
    due_offset_days = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "client",
            "member",
            "invoice_type",
            "invoice_number",
            "issue_date",
            "due_date",
            "due_day",
            "due_offset_days",
            "service_period_start",
            "service_period_end",
            "status",
            "currency",
            "total_cents",
            "external_processor",
            "external_reference",
            "description",
            "notes",
            "metadata",
            "lines",
        ]

    def create(self, validated_data: dict) -> Invoice:
        lines = validated_data.pop("lines", [])
        due_day = validated_data.pop("due_day", None)
        due_offset_days = validated_data.pop("due_offset_days", None)
        if not validated_data.get("due_date"):
            validated_data["due_date"] = calculate_due_date(
                validated_data["issue_date"], due_day=due_day, due_offset_days=due_offset_days
            )
        invoice = Invoice.objects.create(**validated_data)
        line_total = 0
        for line_data in lines:
            quantity = line_data.get("quantity", 1)
            unit_price_cents = line_data.get("unit_price_cents", 0)
            line_total_cents = line_data.get("line_total_cents") or quantity * unit_price_cents
            line_total += line_total_cents
            InvoiceLine.objects.create(
                invoice=invoice,
                amount_cents=line_total_cents,
                line_total_cents=line_total_cents,
                unit_price_cents=unit_price_cents,
                **{key: value for key, value in line_data.items() if key not in {"line_total_cents", "unit_price_cents"}},
            )
        if lines and not validated_data.get("total_cents"):
            invoice.total_cents = line_total
            invoice.save(update_fields=["total_cents", "updated_at"])
        return invoice


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id",
            "client",
            "member",
            "received_at",
            "amount_cents",
            "currency",
            "payment_method",
            "source_type",
            "processor_event_id",
            "processor_charge_id",
            "status",
            "notes",
            "metadata",
        ]


class PaymentAllocationSerializer(serializers.Serializer):
    invoice_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False)


class InvoiceScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceSchedule
        fields = [
            "id",
            "client",
            "member",
            "invoice_type",
            "description",
            "frequency",
            "generation_day",
            "due_day",
            "due_offset_days",
            "amount_cents",
            "active",
            "last_issued_on",
        ]
        read_only_fields = ["id", "last_issued_on"]


class DonationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Donation
        fields = [
            "id",
            "external_charge_id",
            "donor_name",
            "donor_email",
            "amount_cents",
            "net_amount_cents",
            "currency",
            "frequency",
            "donation_date",
            "payment_method",
            "designation",
            "partner_metadata",
            "raw_payload",
        ]


class ExpenseImportSerializer(serializers.Serializer):
    source_name = serializers.CharField()
    parser_key = serializers.CharField()
    csv_content = serializers.CharField()


class ExpenseCategorizeSerializer(serializers.Serializer):
    category_code = serializers.CharField()
    category_name = serializers.CharField()


class ExpenseCategorizationRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategorizationRule
        fields = [
            "id",
            "priority",
            "match_type",
            "pattern",
            "expense_category",
            "vendor_name",
            "active",
        ]


class ImportedBankTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportedBankTransaction
        fields = [
            "id",
            "posted_on",
            "description_raw",
            "amount_cents",
            "direction",
            "currency",
            "is_duplicate",
            "is_reconciled",
            "expense",
        ]


class AccessEventSerializer(serializers.ModelSerializer):
    member_id = serializers.IntegerField(required=False, allow_null=True)

    class Meta:
        model = AccessEvent
        fields = ["credential_uid", "result", "member_id", "details"]


class ReportQuerySerializer(serializers.Serializer):
    from_date = serializers.DateField(required=False)
    to_date = serializers.DateField(required=False)

    def validate(self, attrs: dict) -> dict:
        raw_data = getattr(self, "initial_data", {})
        start = attrs.get("from_date") or raw_data.get("from")
        end = attrs.get("to_date") or raw_data.get("to")
        if not start or not end:
            raise serializers.ValidationError("Both from/to or from_date/to_date are required.")
        if isinstance(start, str):
            start = serializers.DateField().to_internal_value(start)
        if isinstance(end, str):
            end = serializers.DateField().to_internal_value(end)
        attrs["from"] = start
        attrs["to"] = end
        return attrs
