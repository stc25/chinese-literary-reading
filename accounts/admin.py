from django import forms
from django.contrib import admin
from django.contrib.admin.forms import AdminAuthenticationForm

from .models import AllowedLogin


@admin.register(AllowedLogin)
class AllowedLoginAdmin(admin.ModelAdmin):
    list_display = ("entry", "note", "created")
    search_fields = ("entry",)


class EmailAdminLoginForm(AdminAuthenticationForm):
    """The admin login asks for an email address, not a user name."""
    username = forms.EmailField(label="Email address", widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "username"}))


admin.site.login_form = EmailAdminLoginForm
