"""URL configuration."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("accounts.urls")),
    path("django-admin/", admin.site.urls),
    path("", include("app.urls")),
]
