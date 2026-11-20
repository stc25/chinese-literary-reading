"""URL configuration."""
from django.contrib import admin
from django.urls import include, path

from accounts.views import admin_landing

urlpatterns = [
    path("", include("accounts.urls")),
    path("django-admin/", admin_landing, name="admin.landing"),   # staff: the index; others: a landing page
    path("django-admin/", admin.site.urls),
    path("", include("app.urls")),
]

handler404 = "app.views.not_found"   # Django reads it from the root URLconf only
