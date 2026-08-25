from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from trader_portal.admin_site import admin_site

from .forms import AdminUserCreationForm, CustomUserChangeForm
from .models import Profile, User


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    fk_name = "user"
    verbose_name_plural = "perfil"


@admin.register(User, site=admin_site)
class UserAdmin(BaseUserAdmin):
    add_form = AdminUserCreationForm
    form = CustomUserChangeForm
    inlines = (ProfileInline,)
    fieldsets = BaseUserAdmin.fieldsets + ((_("Informações adicionais"), {"fields": ()}),)
    # `email` é obrigatório e único no modelo User: sem ele no formulário de criação,
    # o admin tentaria salvar com e-mail vazio e violaria a constraint no segundo usuário.
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "usable_password", "password1", "password2"),
            },
        ),
    )
    list_display = ("username", "email", "first_name", "last_name", "is_staff")
    list_select_related = ("profile",)
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("email",)

    def get_inline_instances(self, request, obj=None):
        """
        Esconde o inline de Profile na página de adição.

        O Profile é criado automaticamente pelo signal `create_or_update_profile`
        quando o User é salvo. Se o inline aparecesse aqui, o formset tentaria
        inserir um segundo Profile para o mesmo usuário e a criação falhava com
        `IntegrityError: UNIQUE constraint failed: accounts_profile.user_id`.
        Depois de criado, a página de edição mostra o inline normalmente.
        """
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)


@admin.register(Profile, site=admin_site)
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
