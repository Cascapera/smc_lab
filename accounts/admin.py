from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .forms import CustomUserChangeForm, CustomUserCreationForm
from .models import Profile, User


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    fk_name = "user"
    verbose_name_plural = "perfil"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    inlines = (ProfileInline,)
    fieldsets = BaseUserAdmin.fieldsets + (
        (_("Informações adicionais"), {"fields": ()}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets
    list_display = ("username", "email", "first_name", "last_name", "is_staff")
    list_select_related = ("profile",)
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("email",)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_select_related = ("user",)
    list_display = (
        "user",
        "plan",
        "plan_expires_at",
        "primary_market",
        "experience_level",
        "city",
        "state",
        "email_opt_in",
    )
    search_fields = (
        "user__username",
        "user__email",
        "city",
        "state",
        "broker",
    )
    list_filter = ("plan", "primary_market", "experience_level", "email_opt_in")