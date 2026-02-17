from __future__ import annotations

from django import forms
from django.contrib.auth.forms import SetPasswordForm, UserChangeForm, UserCreationForm
from django.utils.safestring import mark_safe

from .models import Profile, User


class SetPasswordFormPT(SetPasswordForm):
    """SetPasswordForm com labels em português."""

    new_password1 = forms.CharField(
        label="Nova senha",
        widget=forms.PasswordInput,
        strip=False,
    )
    new_password2 = forms.CharField(
        label="Confirmar nova senha",
        widget=forms.PasswordInput,
        strip=False,
    )


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
            "timezone": forms.HiddenInput(),
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


def _normalize_digits(value: str) -> str:
    """Remove tudo que não for dígito para comparação."""
    return "".join(c for c in str(value or "") if c.isdigit())


class PasswordRecoveryByDataForm(forms.Form):
    """Formulário para recuperação de senha por e-mail, telefone e CPF."""

    email = forms.EmailField(label="E-mail", required=True)
    phone = forms.CharField(label="Telefone", max_length=20, required=True)
    document_id = forms.CharField(label="CPF", max_length=20, required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone"].widget.attrs["placeholder"] = "(11) 99999-9999"
        self.fields["document_id"].widget.attrs["placeholder"] = "000.000.000-00"

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email")
        phone = cleaned.get("phone")
        document_id = cleaned.get("document_id")

        if not email or not phone or not document_id:
            return cleaned

        from .models import User

        try:
            user = User.objects.get(email__iexact=email.strip())
        except User.DoesNotExist:
            raise forms.ValidationError(
                "Não encontramos uma conta com os dados informados. Verifique e tente novamente."
            )

        profile = getattr(user, "profile", None)
        if not profile:
            raise forms.ValidationError(
                "Não encontramos uma conta com os dados informados. Verifique e tente novamente."
            )

        phone_norm = _normalize_digits(phone)
        doc_norm = _normalize_digits(document_id)

        if not phone_norm or not doc_norm:
            raise forms.ValidationError("Preencha telefone e CPF corretamente.")

        profile_phone_norm = _normalize_digits(profile.phone)
        profile_doc_norm = _normalize_digits(profile.document_id)

        if profile_phone_norm != phone_norm or profile_doc_norm != doc_norm:
            raise forms.ValidationError(
                "Não encontramos uma conta com os dados informados. Verifique e tente novamente."
            )

        cleaned["_user"] = user
        return cleaned
