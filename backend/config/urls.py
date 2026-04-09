from django.contrib import admin
from django.urls import include, path

from api.views import HealthCheckView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", HealthCheckView.as_view()),
    path("", include("api.urls")),
]
