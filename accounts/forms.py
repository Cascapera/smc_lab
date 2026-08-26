from __future__ import annotations

import logging

from django import forms
from django.contrib.auth.forms import (
    AdminUserCreationForm as DjangoAdminUserCreationForm,
)
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm,
    UserChangeForm,
    UserCreationForm,
)
from django.db.models import Q
from django.template import loader
from django.utils.safestring import mark_safe

from .models import Profile, User
from .tasks import send_password_reset_email

logger = logging.getLogger(__name__)


class EmailAuthenticationForm(AuthenticationForm):
    """Formulário de login com label 'E-mail' para o campo username (usado como email)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "E-mail"

    def clean_username(self) -> str:
        """Normaliza o e-mail antes de autenticar.

        O cadastro grava `username` e `email` em minúsculas, mas o
        `AuthenticationForm` entregava o valor cru ao `ModelBackend`. Quem
        digitava `Joao@X.com` recebia 'credenciais inválidas' com a senha certa
        — e ainda consumia uma tentativa do rate limit. A recuperação de senha
        já usava `iexact`, então o login era a única porta case-sensitive.
        """
        return (self.cleaned_data.get("username") or "").strip().lower()


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "first_name", "last_name")


class AdminUserCreationForm(DjangoAdminUserCreationForm):
    """
    Criação de usuário pelo admin.

    Precisa herdar de `AdminUserCreationForm` (e não de `UserCreationForm`) porque
    o `add_fieldsets` padrão do Django 5.1+ inclui o campo `usable_password`, que
    só existe nesta classe. Com o form errado, `/admin/accounts/user/add/` quebrava
    com `FieldError: Unknown field(s) (usable_password)`.

    Não reaproveitamos o `CustomUserCreationForm` porque ele é a base do formulário
    público de cadastro (`UserRegistrationForm`), que não deve ganhar esse campo.
    """

    class Meta(DjangoAdminUserCreationForm.Meta):
        model = User
        fields = ("username", "email")


class CustomUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = ("username", "email", "first_name", "last_name")


class UserRegistrationForm(CustomUserCreationForm):
    password1 = forms.CharField(
        label="Senha",
        strip=False,
        widget=forms.PasswordInput,
        help_text=mark_safe(
            "Sua senha precisa:<br>"
            "• Não ser muito parecida com suas informações pessoais.<br>"
            "• Conter pelo menos 8 caracteres.<br>"
            "• Conter números e letras."
        ),
    )
    password2 = forms.CharField(
        label="Confirmar senha",
        strip=False,
        widget=forms.PasswordInput,
        help_text="Repita a senha para confirmar.",
    )
    email = forms.EmailField(label="E-mail", required=True)

    class Meta(CustomUserCreationForm.Meta):
        model = User
        fields = ("email", "first_name", "last_name")

    def clean_email(self) -> str:
        """Normaliza e checa duplicidade sem depender da caixa.

        O `validate_unique` do ModelForm compara exato e o `.lower()` só
        acontecia no `save()`. Com `joao@x.com` já cadastrado, um POST com
        `Joao@X.com` passava pela validação e estourava `IntegrityError` na
        gravação: 500 na cara de quem estava tentando se cadastrar.
        """
        email = (self.cleaned_data.get("email") or "").strip().lower()
        # `username` também entra na checagem: ele recebe o e-mail no save(), e
        # contas criadas pelo admin podem ter username fora desse formato.
        ja_existe = User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).exists()
        if ja_existe:
            raise forms.ValidationError("Já existe uma conta cadastrada com este e-mail.")
        return email

    def save(self, commit: bool = True):
        user = super().save(commit=False)
        # `clean_email` já normalizou; o username espelha o e-mail para permitir
        # login por e-mail.
        user.email = user.email.strip().lower()
        user.username = user.email
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    terms_accepted = forms.BooleanField(
        label="Aceito os termos de uso",
        required=True,
    )
    privacy_accepted = forms.BooleanField(
        label="Aceito a política de privacidade",
        required=True,
    )
    timezone = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
        initial="America/Sao_Paulo",
    )

    class Meta:
        model = Profile
        exclude = (
            "user",
            "terms_accepted_at",
            "privacy_accepted_at",
            "plan",
            "plan_expires_at",
            "last_reset_at",
            "created_at",
            "updated_at",
            # Discord é preenchido ao vincular a conta depois do cadastro
            "discord_user_id",
            "discord_username",
            "discord_connected_at",
        )
        widgets = {
            "phone": forms.TextInput(attrs={"placeholder": "(11) 99999-9999"}),
            "country": forms.TextInput(attrs={"placeholder": "Brasil"}),
            "zipcode": forms.TextInput(attrs={"placeholder": "00000-000"}),
        }

    def clean_country(self) -> str:
        country = self.cleaned_data.get("country", "")
        return country.upper()

    def clean_timezone(self) -> str:
        # Garante um valor padrão caso o campo esteja oculto
        return self.cleaned_data.get("timezone") or "America/Sao_Paulo"


class ProfileEditForm(forms.ModelForm):
    class Meta:
        model = Profile
        exclude = (
            "user",
            "terms_accepted",
            "privacy_accepted",
            "terms_accepted_at",
            "privacy_accepted_at",
            "plan",
            "plan_expires_at",
            "last_reset_at",
            "created_at",
            "updated_at",
            # Discord é preenchido pela integração, não editável pelo usuário
            "discord_user_id",
            "discord_username",
            "discord_connected_at",
        )
        widgets = {
            "phone": forms.TextInput(attrs={"placeholder": "(11) 99999-9999"}),
            "country": forms.TextInput(attrs={"placeholder": "Brasil"}),
            "zipcode": forms.TextInput(attrs={"placeholder": "00000-000"}),
            "timezone": forms.HiddenInput(),
        }

    def clean_country(self) -> str:
        country = self.cleaned_data.get("country", "")
        return country.upper()

    def clean_timezone(self) -> str:
        return self.cleaned_data.get("timezone") or "America/Sao_Paulo"


class AsyncPasswordResetForm(PasswordResetForm):
    """Recuperação de senha que sai do request antes de falar com o SMTP.

    O `PasswordResetForm` do Django envia o e-mail dentro do `save()`, ou seja,
    dentro da requisição. Renderizamos aqui (o contexto tem o objeto `User`, que
    não vai para a fila) e enfileiramos só o texto pronto.

    Se o broker estiver fora, cai para o envio síncrono: é preferível uma
    requisição lenta a um usuário trancado fora da própria conta.
    """

    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ) -> None:
        subject = "".join(loader.render_to_string(subject_template_name, context).splitlines())
        body = loader.render_to_string(email_template_name, context)
        html_body = (
            loader.render_to_string(html_email_template_name, context)
            if html_email_template_name
            else None
        )

        try:
            send_password_reset_email.delay(subject, body, from_email, to_email, html_body)
        except Exception as exc:
            logger.error(
                "[accounts] Falha ao enfileirar e-mail de recuperação; enviando no request: %s",
                exc,
                exc_info=True,
            )
            super().send_mail(
                subject_template_name,
                email_template_name,
                context,
                from_email,
                to_email,
                html_email_template_name,
            )
