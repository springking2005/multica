"""Django admin registrations for accounts."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import (
    Daemon,
    DaemonToken,
    Invitation,
    Member,
    NotificationPreference,
    PersonalAccessToken,
    User,
    VerificationCode,
    Workspace,
)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = ("email", "name", "is_staff", "is_active", "created_at")
    search_fields = ("email", "name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("name", "avatar_url", "language", "onboarded_at", "onboarding_questionnaire")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "name", "password1", "password2")}),)
    readonly_fields = ("created_at", "updated_at")


admin.site.register(Workspace)
admin.site.register(Member)
admin.site.register(Invitation)
admin.site.register(PersonalAccessToken)
admin.site.register(VerificationCode)
admin.site.register(NotificationPreference)
admin.site.register(Daemon)
admin.site.register(DaemonToken)
