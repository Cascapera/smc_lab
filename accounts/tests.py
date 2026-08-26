"""
Testes do app accounts - autenticação, perfis e registro.

"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .discord_links import resolve_duplicate_discord_links
from .forms import EmailAuthenticationForm, ProfileEditForm, ProfileForm, UserRegistrationForm
from .models import (
    ExperienceLevel,
    Plan,
    PrimaryMarket,
    Profile,
    TradingStyle,
    User,
)
from .ratelimit import real_client_ip

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
        user = User.objects.create_user(
            username="anon@test.com", email="anon@test.com", password="x"
        )
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
                "experience_level": ExperienceLevel.BEGINNER,
                "primary_market": PrimaryMarket.INDEX_FUTURES,
                "trading_style": TradingStyle.DAY_TRADE,
                "email_opt_in": True,
                "initial_balance": "0",
                "current_balance": "0",
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
                "experience_level": ExperienceLevel.BEGINNER,
                "primary_market": PrimaryMarket.INDEX_FUTURES,
                "trading_style": TradingStyle.DAY_TRADE,
                "email_opt_in": True,
                "initial_balance": "0",
                "current_balance": "0",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["country"], "BR")

    def test_clean_timezone_default_quando_vazio(self):
        form = ProfileForm(
            data={
                "terms_accepted": True,
                "privacy_accepted": True,
                "country": "BR",
                "timezone": "",
                "experience_level": ExperienceLevel.BEGINNER,
                "primary_market": PrimaryMarket.INDEX_FUTURES,
                "trading_style": TradingStyle.DAY_TRADE,
                "email_opt_in": True,
                "initial_balance": "0",
                "current_balance": "0",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
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
                "experience_level": ExperienceLevel.BEGINNER,
                "primary_market": PrimaryMarket.INDEX_FUTURES,
                "trading_style": TradingStyle.DAY_TRADE,
                "email_opt_in": True,
                "initial_balance": "0",
                "current_balance": "0",
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


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


class UserAdminTest(TestCase):
    """
    Testes do admin de usuários.

    Regressão: `add_fieldsets` do Django 5.1+ inclui `usable_password`, campo que
    só existe em `AdminUserCreationForm`. Com `UserCreationForm` como `add_form`,
    a página de criação quebrava com FieldError e nenhum usuário podia ser criado
    pelo admin.
    """

    def setUp(self):
        self.admin = create_user(
            email="admin@test.com",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.admin)

    def test_pagina_de_adicionar_usuario_carrega(self):
        response = self.client.get(reverse("admin:accounts_user_add"))
        self.assertEqual(response.status_code, 200)

    def test_formulario_de_adicao_pede_email(self):
        """E-mail é obrigatório e único no modelo; precisa estar no formulário."""
        response = self.client.get(reverse("admin:accounts_user_add"))
        self.assertIn("email", response.context["adminform"].form.fields)

    def test_cria_usuario_pelo_admin(self):
        """
        Regressão: o inline de Profile era renderizado na página de adição e o
        formset tentava criar um segundo Profile (o signal já cria um), fazendo
        a criação estourar IntegrityError mesmo com o formulário válido.
        """
        response = self.client.post(
            reverse("admin:accounts_user_add"),
            {
                "username": "novo@test.com",
                "email": "novo@test.com",
                "usable_password": "true",
                "password1": "SenhaForte123",
                "password2": "SenhaForte123",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="novo@test.com")
        self.assertEqual(Profile.objects.filter(user=user).count(), 1)

    def test_pagina_de_edicao_mostra_inline_de_profile(self):
        """O inline some só na adição; na edição ele continua disponível."""
        user = create_user(email="editar@test.com")
        response = self.client.get(reverse("admin:accounts_user_change", args=[user.pk]))
        self.assertEqual(response.status_code, 200)
        prefixes = [fs.formset.prefix for fs in response.context["inline_admin_formsets"]]
        self.assertIn("profile", prefixes)

    def test_changelist_de_usuarios_carrega(self):
        response = self.client.get(reverse("admin:accounts_user_changelist"))
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# Rate limit por IP real (A5)
# ---------------------------------------------------------------------------


class RealClientIpTest(TestCase):
    """A chave de rate limit lê o header que o nginx escreve."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_usa_x_real_ip_quando_presente(self):
        request = self.factory.post("/", HTTP_X_REAL_IP="203.0.113.10", REMOTE_ADDR="127.0.0.1")
        self.assertEqual(real_client_ip(request), "203.0.113.10")

    def test_cai_para_remote_addr_quando_header_ausente(self):
        request = self.factory.post("/", REMOTE_ADDR="127.0.0.1")
        self.assertEqual(real_client_ip(request), "127.0.0.1")

    def test_cai_para_remote_addr_quando_header_nao_e_ip(self):
        """Valor inválido não pode virar bucket de rate limit."""
        request = self.factory.post("/", HTTP_X_REAL_IP="nao-e-ip", REMOTE_ADDR="127.0.0.1")
        self.assertEqual(real_client_ip(request), "127.0.0.1")

    def test_aceita_ipv6(self):
        request = self.factory.post("/", HTTP_X_REAL_IP="2001:db8::1", REMOTE_ADDR="127.0.0.1")
        self.assertEqual(real_client_ip(request), "2001:db8::1")


@override_settings(RATELIMIT_ENABLE=True)
class RateLimitPorIpRealTest(TestCase):
    """
    Regressão de A5.

    Com `key="ip"` (REMOTE_ADDR), atrás do nginx todos os clientes caíam no
    mesmo bucket: cinco POSTs bloqueavam o login do site inteiro. Estes testes
    falham naquela versão.
    """

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        create_user(email="vitima@example.com", password="SenhaForte123")

    def _post_login(self, ip: str):
        return self.client.post(
            reverse("accounts:login"),
            {"username": "vitima@example.com", "password": "senha-errada"},
            HTTP_X_REAL_IP=ip,
        )

    def test_ip_que_estoura_o_limite_e_bloqueado(self):
        for _ in range(5):
            self.assertEqual(self._post_login("203.0.113.1").status_code, 200)

        response = self._post_login("203.0.113.1")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:login"))

    def test_ip_bloqueado_nao_bloqueia_os_demais_usuarios(self):
        for _ in range(6):
            self._post_login("203.0.113.1")

        response = self._post_login("198.51.100.7")

        # 200 = formulário de login processado (credencial errada).
        # 302 seria a mensagem de "muitas tentativas" — o bug do A5.
        self.assertEqual(response.status_code, 200)

    def test_registro_tambem_limita_por_ip_real(self):
        url = reverse("accounts:register")
        for _ in range(3):
            self.client.post(url, {}, HTTP_X_REAL_IP="203.0.113.2")

        bloqueado = self.client.post(url, {}, HTTP_X_REAL_IP="203.0.113.2")
        outro_ip = self.client.post(url, {}, HTTP_X_REAL_IP="198.51.100.9")

        self.assertEqual(bloqueado.status_code, 302)
        self.assertEqual(outro_ip.status_code, 200)


# ---------------------------------------------------------------------------
# Unicidade de discord_user_id (A6)
# ---------------------------------------------------------------------------


class DiscordUserIdUniqueConstraintTest(TestCase):
    """A constraint vale para ids reais e ignora perfis sem Discord."""

    def test_dois_perfis_com_o_mesmo_discord_id_violam_a_constraint(self):
        primeiro = create_user(email="a@example.com").profile
        primeiro.discord_user_id = "discord_1"
        primeiro.save()

        segundo = create_user(email="b@example.com").profile
        segundo.discord_user_id = "discord_1"

        with self.assertRaises(IntegrityError), transaction.atomic():
            segundo.save()

    def test_varios_perfis_sem_discord_convivem(self):
        create_user(email="c@example.com")
        create_user(email="d@example.com")

        self.assertEqual(Profile.objects.filter(discord_user_id="").count(), 2)


class ResolveDuplicateDiscordLinksTest(TestCase):
    """
    Desempate dos duplicados que já estavam no banco.

    A constraint é removida durante estes testes porque o estado que a função
    existe para resolver é anterior a ela — é exatamente o que a migração de
    dados encontra em produção, antes do `AddConstraint`.
    """

    def setUp(self):
        # A constraint condicional é criada como índice único (SQLite e
        # Postgres), então derrubar o índice basta para reproduzir o estado
        # anterior a ela. Fica dentro da transação do teste: o rollback do
        # TestCase recria. O schema_editor não serve aqui — o SQLite recusa DDL
        # dentro de uma transação já aberta.
        with connection.cursor() as cursor:
            cursor.execute("DROP INDEX perfil_discord_user_id_unico")

    def _perfil(self, email: str, discord_id: str, **kwargs) -> Profile:
        profile = create_user(email=email).profile
        profile.discord_user_id = discord_id
        profile.discord_username = email.split("@")[0]
        for campo, valor in kwargs.items():
            setattr(profile, campo, valor)
        profile.save()
        return profile

    def test_pagante_vence_o_free_mais_recente(self):
        agora = timezone.now()
        pagante = self._perfil(
            "pagante@example.com",
            "discord_x",
            plan=Plan.PREMIUM,
            discord_connected_at=agora - timedelta(days=30),
        )
        free = self._perfil(
            "free@example.com",
            "discord_x",
            plan=Plan.FREE,
            discord_connected_at=agora,
        )

        resolve_duplicate_discord_links(Profile)

        pagante.refresh_from_db()
        free.refresh_from_db()
        self.assertEqual(pagante.discord_user_id, "discord_x")
        self.assertEqual(free.discord_user_id, "")
        self.assertEqual(free.discord_username, "")
        self.assertIsNone(free.discord_connected_at)

    def test_entre_dois_free_vence_o_vinculo_mais_recente(self):
        agora = timezone.now()
        antigo = self._perfil(
            "antigo@example.com", "discord_y", discord_connected_at=agora - timedelta(days=10)
        )
        recente = self._perfil("recente@example.com", "discord_y", discord_connected_at=agora)

        resolve_duplicate_discord_links(Profile)

        antigo.refresh_from_db()
        recente.refresh_from_db()
        self.assertEqual(recente.discord_user_id, "discord_y")
        self.assertEqual(antigo.discord_user_id, "")

    def test_plano_expirado_nao_conta_como_pagante(self):
        agora = timezone.now()
        expirado = self._perfil(
            "expirado@example.com",
            "discord_z",
            plan=Plan.PREMIUM,
            plan_expires_at=agora - timedelta(days=1),
            discord_connected_at=agora - timedelta(days=5),
        )
        free_recente = self._perfil("recente2@example.com", "discord_z", discord_connected_at=agora)

        resolve_duplicate_discord_links(Profile)

        expirado.refresh_from_db()
        free_recente.refresh_from_db()
        self.assertEqual(free_recente.discord_user_id, "discord_z")
        self.assertEqual(expirado.discord_user_id, "")

    def test_perfil_sem_duplicata_fica_intacto(self):
        sozinho = self._perfil("sozinho@example.com", "discord_unico")

        limpos = resolve_duplicate_discord_links(Profile)

        sozinho.refresh_from_db()
        self.assertEqual(limpos, [])
        self.assertEqual(sozinho.discord_user_id, "discord_unico")

    def test_resultado_permite_criar_a_constraint(self):
        """Depois da limpeza, nenhum id repetido sobra."""
        self._perfil("um@example.com", "discord_w", plan=Plan.BASIC)
        self._perfil("dois@example.com", "discord_w")
        self._perfil("tres@example.com", "discord_w")

        resolve_duplicate_discord_links(Profile)

        restantes = Profile.objects.exclude(discord_user_id="").values_list(
            "discord_user_id", flat=True
        )
        self.assertEqual(sorted(restantes), ["discord_w"])
