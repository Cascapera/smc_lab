"""
Testes do app accounts - autenticação, perfis e registro.

"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import EmailAuthenticationForm, ProfileEditForm, ProfileForm, UserRegistrationForm
from .models import (
    ExperienceLevel,
    Plan,
    PrimaryMarket,
    Profile,
    TradingStyle,
    User,
)


# ---------------------------------------------------------------------------
# Factories / Fixtures
# ---------------------------------------------------------------------------


def create_user(
    email: str = "user@example.com",
    password: str = "SenhaForte123",
    first_name: str = "João",
    last_name: str = "Silva",
    is_staff: bool = False,
    is_superuser: bool = False,
) -> User:
    """Cria usuário para testes."""
    user = User.objects.create_user(
        username=email.lower(),
        email=email.lower(),
        password=password,
        first_name=first_name,
        last_name=last_name,
        is_staff=is_staff,
        is_superuser=is_superuser,
    )
    return user


def create_profile(user: User, plan: str = Plan.FREE, **kwargs) -> Profile:
    """Cria ou retorna profile com dados customizados."""
    profile = user.profile
    for key, value in kwargs.items():
        if hasattr(profile, key):
            setattr(profile, key, value)
    profile.plan = plan
    profile.save()
    return profile


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class UserModelTest(TestCase):
    """Testes do modelo User."""

    def test_str_retorna_nome_completo(self):
        user = create_user(first_name="Maria", last_name="Santos")
        self.assertEqual(str(user), "Maria Santos")

    def test_str_fallback_para_username_quando_sem_nome(self):
        user = User.objects.create_user(username="anon@test.com", email="anon@test.com", password="x")
        user.first_name = ""
        user.last_name = ""
        user.save()
        self.assertEqual(str(user), "anon@test.com")

    def test_email_unico(self):
        create_user(email="unique@test.com")
        with self.assertRaises(Exception):
            User.objects.create_user(username="outro", email="unique@test.com", password="x")


class ProfileModelTest(TestCase):
    """Testes do modelo Profile."""

    def setUp(self):
        self.user = create_user()

    def test_profile_criado_por_signal_ao_criar_user(self):
        self.assertTrue(hasattr(self.user, "profile"))
        self.assertIsInstance(self.user.profile, Profile)

    def test_str_retorna_perfil_de_user(self):
        self.assertEqual(str(self.user.profile), f"Perfil de {self.user}")

    def test_active_plan_retorna_plano_quando_nao_expirado(self):
        profile = create_profile(self.user, plan=Plan.PREMIUM)
        self.assertEqual(profile.active_plan(), Plan.PREMIUM)

    def test_active_plan_retorna_free_quando_expirado(self):
        profile = create_profile(self.user, plan=Plan.PREMIUM)
        profile.plan_expires_at = timezone.now() - timezone.timedelta(days=1)
        profile.save()
        self.assertEqual(profile.active_plan(), Plan.FREE)

    def test_has_plan_at_least_basic_com_plano_free_retorna_false(self):
        profile = create_profile(self.user, plan=Plan.FREE)
        self.assertFalse(profile.has_plan_at_least(Plan.BASIC))

    def test_has_plan_at_least_basic_com_plano_premium_retorna_true(self):
        profile = create_profile(self.user, plan=Plan.PREMIUM)
        self.assertTrue(profile.has_plan_at_least(Plan.BASIC))

    def test_has_plan_at_least_premium_plus_com_plano_premium_retorna_false(self):
        profile = create_profile(self.user, plan=Plan.PREMIUM)
        self.assertFalse(profile.has_plan_at_least(Plan.PREMIUM_PLUS))

    def test_has_plan_at_least_plano_desconhecido_retorna_false(self):
        """Plano inválido ou desconhecido não concede acesso."""
        profile = create_profile(self.user, plan=Plan.FREE)
        self.assertFalse(profile.has_plan_at_least("plano_invalido"))

    def test_get_active_plan_display_retorna_label(self):
        profile = create_profile(self.user, plan=Plan.BASIC)
        self.assertEqual(profile.get_active_plan_display(), "Basic")

    def test_reset_balance_atualiza_saldos(self):
        profile = create_profile(self.user)
        profile.initial_balance = Decimal("1000.00")
        profile.current_balance = Decimal("1500.00")
        profile.save()

        profile.reset_balance(Decimal("2000.00"))

        profile.refresh_from_db()
        self.assertEqual(profile.initial_balance, Decimal("2000.00"))
        self.assertEqual(profile.current_balance, Decimal("2000.00"))
        self.assertIsNotNone(profile.last_reset_at)


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------


class EmailAuthenticationFormTest(TestCase):
    """Testes do EmailAuthenticationForm (login com label E-mail)."""

    def test_campo_username_tem_label_email(self):
        form = EmailAuthenticationForm()
        self.assertEqual(form.fields["username"].label, "E-mail")


class UserRegistrationFormTest(TestCase):
    """Testes do UserRegistrationForm."""

    def test_save_define_username_como_email_lowercase(self):
        form = UserRegistrationForm(
            data={
                "email": "Test@Example.COM",
                "first_name": "Test",
                "last_name": "User",
                "password1": "SenhaForte123",
                "password2": "SenhaForte123",
            }
        )
        self.assertTrue(form.is_valid())
        user = form.save()
        self.assertEqual(user.username, "test@example.com")
        self.assertEqual(user.email, "test@example.com")

    def test_senhas_diferentes_invalido(self):
        form = UserRegistrationForm(
            data={
                "email": "test@example.com",
                "first_name": "Test",
                "last_name": "User",
                "password1": "SenhaForte123",
                "password2": "OutraSenha456",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)

    def test_email_obrigatorio(self):
        form = UserRegistrationForm(
            data={
                "email": "",
                "first_name": "Test",
                "last_name": "User",
                "password1": "SenhaForte123",
                "password2": "SenhaForte123",
            }
        )
        self.assertFalse(form.is_valid())


class ProfileFormTest(TestCase):
    """Testes do ProfileForm (registro)."""

    def test_terms_e_privacy_obrigatorios(self):
        form = ProfileForm(
            data={
                "terms_accepted": False,
                "privacy_accepted": False,
                "country": "BR",
                "timezone": "America/Sao_Paulo",
            }
        )
        self.assertFalse(form.is_valid())

    def test_clean_country_retorna_uppercase(self):
        form = ProfileForm(
            data={
                "terms_accepted": True,
                "privacy_accepted": True,
                "country": "br",
                "timezone": "America/Sao_Paulo",
            }
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["country"], "BR")

    def test_clean_timezone_default_quando_vazio(self):
        form = ProfileForm(
            data={
                "terms_accepted": True,
                "privacy_accepted": True,
                "country": "BR",
                "timezone": "",
            }
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["timezone"], "America/Sao_Paulo")


class ProfileEditFormTest(TestCase):
    """Testes do ProfileEditForm."""

    def setUp(self):
        self.user = create_user()
        self.profile = self.user.profile

    def test_nao_inclui_campos_discord(self):
        """Campos Discord não devem ser editáveis pelo usuário."""
        form = ProfileEditForm(instance=self.profile)
        self.assertNotIn("discord_user_id", form.fields)
        self.assertNotIn("discord_username", form.fields)
        self.assertNotIn("discord_connected_at", form.fields)

    def test_salva_alteracoes_no_perfil(self):
        form = ProfileEditForm(
            instance=self.profile,
            data={
                "phone": "11999999999",
                "city": "São Paulo",
                "state": "SP",
                "country": "BR",
                "timezone": "America/Sao_Paulo",
                "experience_level": ExperienceLevel.BEGINNER,
                "primary_market": PrimaryMarket.INDEX_FUTURES,
                "trading_style": TradingStyle.DAY_TRADE,
                "email_opt_in": True,
                "initial_balance": "0",
                "current_balance": "0",
            },
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.city, "São Paulo")
        self.assertEqual(self.profile.phone, "11999999999")


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


class RegisterViewTest(TestCase):
    """Testes da RegisterView."""

    def test_get_retorna_200_com_formularios_vazios(self):
        response = self.client.get(reverse("accounts:register"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("user_form", response.context)
        self.assertIn("profile_form", response.context)

    def test_post_valido_cria_usuario_e_redireciona_para_login(self):
        response = self.client.post(
            reverse("accounts:register"),
            data={
                "email": "novo@example.com",
                "first_name": "Novo",
                "last_name": "Usuario",
                "password1": "SenhaForte123",
                "password2": "SenhaForte123",
                "terms_accepted": "on",
                "privacy_accepted": "on",
                "country": "BR",
                "timezone": "America/Sao_Paulo",
            },
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:login"))

        user = User.objects.get(email="novo@example.com")
        self.assertEqual(user.username, "novo@example.com")
        self.assertTrue(user.profile.terms_accepted)
        self.assertTrue(user.profile.privacy_accepted)
        self.assertIsNotNone(user.profile.terms_accepted_at)

    def test_post_invalido_retorna_formulario_com_erros(self):
        response = self.client.post(
            reverse("accounts:register"),
            data={
                "email": "invalido",
                "password1": "123",
                "password2": "456",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["user_form"].is_valid())


class LogoutViewTest(TestCase):
    """Testes da LogoutView."""

    def test_get_desloga_e_redireciona_para_landing(self):
        user = create_user()
        self.client.force_login(user)
        response = self.client.get(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("landing"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_post_desloga_e_redireciona_para_landing(self):
        user = create_user()
        self.client.force_login(user)
        response = self.client.post(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("landing"))


class ProfileViewTest(TestCase):
    """Testes da ProfileView."""

    def test_anonimo_redireciona_para_login(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_autenticado_retorna_200_com_contexto(self):
        user = create_user()
        self.client.force_login(user)
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["user_obj"], user)
        self.assertEqual(response.context["profile"], user.profile)


class ProfileEditViewTest(TestCase):
    """Testes da ProfileEditView."""

    def setUp(self):
        self.user = create_user()
        self.profile = self.user.profile

    def test_anonimo_redireciona_para_login(self):
        response = self.client.get(reverse("accounts:profile_edit"))
        self.assertEqual(response.status_code, 302)

    def test_get_retorna_formulario_preenchido(self):
        self.client.force_login(self.user)
        self.profile.city = "Rio de Janeiro"
        self.profile.save()

        response = self.client.get(reverse("accounts:profile_edit"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].instance, self.profile)

    def test_post_valido_atualiza_perfil_e_redireciona(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("accounts:profile_edit"),
            data={
                "phone": "21987654321",
                "city": "Niterói",
                "state": "RJ",
                "country": "BR",
                "timezone": "America/Sao_Paulo",
                "experience_level": ExperienceLevel.BEGINNER,
                "primary_market": PrimaryMarket.INDEX_FUTURES,
                "trading_style": TradingStyle.DAY_TRADE,
                "email_opt_in": True,
                "initial_balance": "0",
                "current_balance": "0",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:profile"))

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.city, "Niterói")


class SessionStatusViewTest(TestCase):
    """Testes da SessionStatusView."""

    def test_anonimo_retorna_401(self):
        response = self.client.get(reverse("accounts:session_status"))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "unauthorized")

    def test_autenticado_retorna_json_com_last_login(self):
        user = create_user()
        self.client.force_login(user)
        response = self.client.get(reverse("accounts:session_status"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("last_login", data)
        self.assertIn("last_login_ts", data)


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------


def _add_session_and_messages(request):
    """Adiciona session e messages ao request (necessário para RequestFactory)."""
    SessionMiddleware(lambda r: r).process_request(request)
    MessageMiddleware(lambda r: r).process_request(request)
    request.session.save()
    return request


class PlanRequiredMixinTest(TestCase):
    """Testes do PlanRequiredMixin."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user_free = create_user(email="free@test.com")
        create_profile(self.user_free, plan=Plan.FREE)
        self.user_basic = create_user(email="basic@test.com")
        create_profile(self.user_basic, plan=Plan.BASIC)
        self.user_premium = create_user(email="premium@test.com")
        create_profile(self.user_premium, plan=Plan.PREMIUM)

    def _view_protected_by_plan(self, plan: str):
        """View fictícia protegida por plano para teste."""
        from django.http import HttpResponse
        from django.views import View

        from .mixins import PlanRequiredMixin

        class TestView(PlanRequiredMixin, View):
            def get(self, request):
                return HttpResponse("OK")

        TestView.required_plan = plan
        return TestView.as_view()

    def test_usuario_free_redirecionado_ao_acessar_recurso_basic(self):
        view = self._view_protected_by_plan(Plan.BASIC)
        request = _add_session_and_messages(self.factory.get("/test/"))
        request.user = self.user_free

        response = view(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("trades:dashboard"))

    def test_usuario_basic_acessa_recurso_basic(self):
        view = self._view_protected_by_plan(Plan.BASIC)
        request = _add_session_and_messages(self.factory.get("/test/"))
        request.user = self.user_basic

        response = view(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")

    def test_usuario_premium_acessa_recurso_basic(self):
        view = self._view_protected_by_plan(Plan.BASIC)
        request = _add_session_and_messages(self.factory.get("/test/"))
        request.user = self.user_premium

        response = view(request)
        self.assertEqual(response.status_code, 200)


class StaffRequiredMixinTest(TestCase):
    """Testes do StaffRequiredMixin."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user_normal = create_user(email="normal@test.com")
        self.user_staff = create_user(email="staff@test.com", is_staff=True)

    def _view_protected_by_staff(self):
        from django.http import HttpResponse
        from django.views import View

        from .mixins import StaffRequiredMixin

        class TestView(StaffRequiredMixin, View):
            def get(self, request):
                return HttpResponse("OK")

        return TestView.as_view()

    def test_usuario_normal_redirecionado(self):
        view = self._view_protected_by_staff()
        request = _add_session_and_messages(self.factory.get("/test/"))
        request.user = self.user_normal

        response = view(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("trades:dashboard"))

    def test_usuario_staff_acessa(self):
        view = self._view_protected_by_staff()
        request = _add_session_and_messages(self.factory.get("/test/"))
        request.user = self.user_staff

        response = view(request)
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


class CreateProfileSignalTest(TestCase):
    """Testes do signal create_or_update_profile."""

    def test_profile_criado_automaticamente_ao_criar_user(self):
        user = User.objects.create_user(
            username="signal@test.com",
            email="signal@test.com",
            password="SenhaForte123",
        )
        self.assertTrue(Profile.objects.filter(user=user).exists())
        self.assertEqual(user.profile.user, user)
