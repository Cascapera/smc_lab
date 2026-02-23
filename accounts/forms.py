from __future__ import annotations

from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    UserChangeForm,
    UserCreationForm,
)
from django.utils.safestring import mark_safe

from .models import Profile, User


class EmailAuthenticationForm(AuthenticationForm):
    """Formulário de login com label 'E-mail' para o campo username (usado como email)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "E-mail"


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "first_name", "last_name")


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

    def save(self, commit: bool = True):
        user = super().save(commit=False)
        # Usa o e-mail como username para permitir login por e-mail
        user.username = user.email.lower()
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
