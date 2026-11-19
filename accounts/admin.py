from django.contrib import admin

from .models import AllowedLogin


@admin.register(AllowedLogin)
class AllowedLoginAdmin(admin.ModelAdmin):
    list_display = ("entry", "note", "created")
    search_fields = ("entry",)
