from django.contrib import admin

from apps.access.models import AccessAllowlistSnapshot, AccessEvent, RFIDCredential

admin.site.register(RFIDCredential)
admin.site.register(AccessAllowlistSnapshot)
admin.site.register(AccessEvent)
