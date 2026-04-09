from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class Client(models.Model):
    class ClientType(models.TextChoices):
        PERSON = "PERSON", "Person"
        ORGANIZATION = "ORGANIZATION", "Organization"

    client_type = models.CharField(max_length=20, choices=ClientType.choices, default=ClientType.PERSON)
    display_name_text = models.CharField(max_length=255, blank=True)
    legal_name = models.CharField(max_length=255, blank=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    organization_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=50, blank=True)
    address_line_1 = models.CharField(max_length=255, blank=True)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=30, blank=True)
    country = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["last_name", "first_name", "organization_name", "id"]

    def __str__(self) -> str:
        return self.display_name

    @property
    def display_name(self) -> str:
        if self.display_name_text:
            return self.display_name_text
        if self.organization_name:
            return self.organization_name
        name = f"{self.first_name} {self.last_name}".strip()
        return name or self.email

    @property
    def primary_email(self) -> str:
        return self.email

    @primary_email.setter
    def primary_email(self, value: str) -> None:
        self.email = value

    @property
    def primary_phone(self) -> str:
        return self.phone

    @primary_phone.setter
    def primary_phone(self, value: str) -> None:
        self.phone = value

    @property
    def address_line1(self) -> str:
        return self.address_line_1

    @address_line1.setter
    def address_line1(self, value: str) -> None:
        self.address_line_1 = value

    @property
    def address_line2(self) -> str:
        return self.address_line_2

    @address_line2.setter
    def address_line2(self, value: str) -> None:
        self.address_line_2 = value


class ClientAlias(models.Model):
    class AliasType(models.TextChoices):
        NAME = "NAME", "Name"
        EMAIL = "EMAIL", "Email"
        PHONE = "PHONE", "Phone"
        ADDRESS = "ADDRESS", "Address"

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="aliases")
    alias_type = models.CharField(max_length=20, choices=AliasType.choices)
    value = models.CharField(max_length=255)
    valid_from = models.DateField(default=timezone.now)
    valid_to = models.DateField(blank=True, null=True)

    class Meta:
        ordering = ["-valid_from", "-id"]


class Member(models.Model):
    class MembershipClass(models.TextChoices):
        FULL = "FULL", "Full"
        HARDSHIP = "HARDSHIP", "Hardship"

    class Status(models.TextChoices):
        APPLICANT = "APPLICANT", "Applicant"
        ACTIVE = "ACTIVE", "Active"
        PAST_DUE = "PAST_DUE", "Past due"
        SUSPENDED = "SUSPENDED", "Suspended"
        LEFT = "LEFT", "Left"

    client = models.OneToOneField(Client, on_delete=models.CASCADE, related_name="member")
    member_number = models.CharField(max_length=50, unique=True, blank=True, null=True)
    membership_class = models.CharField(max_length=20, choices=MembershipClass.choices, default=MembershipClass.FULL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.APPLICANT)
    voting_eligible = models.BooleanField(default=True)
    door_access_enabled = models.BooleanField(default=False)
    joined_at = models.DateField(default=timezone.now)
    left_at = models.DateField(blank=True, null=True)
    dues_override_cents = models.PositiveIntegerField(blank=True, null=True)
    autopay_enabled = models.BooleanField(default=False)
    stripe_customer_id = models.CharField(max_length=255, blank=True)
    default_payment_method_id = models.CharField(max_length=255, blank=True)
    autopay_payment_method = models.ForeignKey(
        "billing.ProcessorPaymentMethod",
        on_delete=models.SET_NULL,
        related_name="autopay_members",
        blank=True,
        null=True,
    )
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["client__last_name", "client__first_name", "id"]

    def __str__(self) -> str:
        return f"Member #{self.pk} {self.client.display_name}"

    def dues_amount_cents(self) -> int:
        if self.dues_override_cents and self.dues_override_cents > 0:
            return self.dues_override_cents
        if self.membership_class == self.MembershipClass.HARDSHIP:
            return settings.MEMBER_DUES_HARDSHIP_RATE_CENTS
        return settings.MEMBER_DUES_FULL_RATE_CENTS


class MembershipTerm(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="membership_terms")
    effective_from = models.DateField()
    effective_to = models.DateField(blank=True, null=True)
    membership_class = models.CharField(max_length=20, choices=Member.MembershipClass.choices)
    monthly_dues_cents = models.PositiveIntegerField()
    voting_eligible = models.BooleanField(default=True)
    door_access_enabled = models.BooleanField(default=False)
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_from", "-id"]
