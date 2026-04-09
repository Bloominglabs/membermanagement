from django.contrib import admin

from apps.members.models import Client, Member


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("id", "display_name", "email", "phone")
    search_fields = ("first_name", "last_name", "organization_name", "email")


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("id", "client", "membership_class", "status", "autopay_enabled")
    list_filter = ("membership_class", "status", "autopay_enabled")
    search_fields = ("client__first_name", "client__last_name", "client__email")
