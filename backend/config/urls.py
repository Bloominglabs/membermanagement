from django.contrib import admin
from django.urls import include, path

from api.views import HealthCheckView
from apps.staffops.views import payment_cancel, payment_success

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", HealthCheckView.as_view()),
    path("payments/success", payment_success),
    path("payments/cancel", payment_cancel),
    path("staff/", include("apps.staffops.urls")),
    path("", include("api.urls")),
]
