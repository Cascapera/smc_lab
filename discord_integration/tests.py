"""
Testes do app discord_integration - OAuth, services e views.
"""

from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Plan
from accounts.tests import create_profile, create_user
from trader_portal.celery import app as celery_app

from .services import (
    MAX_ESPERA_429_SEGUNDOS,
    MAX_TENTATIVAS_429,
    DiscordRateLimited,
    _bot_request,
    _discord_rate_limiter,
    build_oauth_url,
    desired_role_for_plan,
    sync_profile_roles,
)

# ---------------------------------------------------------------------------
# Services - build_oauth_url
# ---------------------------------------------------------------------------


class BuildOAuthUrlTest(TestCase):
    """Testes de build_oauth_url."""

    @patch("discord_integration.services.settings")
    def test_retorna_url_com_state_e_scope(self, mock_settings):
        mock_settings.DISCORD_CLIENT_ID = "client_123"
        mock_settings.DISCORD_CLIENT_SECRET = "secret"
        mock_settings.DISCORD_REDIRECT_URI = "https://example.com/callback"
        mock_settings.DISCORD_BOT_TOKEN = ""
        mock_settings.DISCORD_GUILD_ID = ""
        mock_settings.DISCORD_ROLE_BASIC_ID = ""
        mock_settings.DISCORD_ROLE_PREMIUM_ID = ""
        mock_settings.DISCORD_ROLE_PREMIUM_PLUS_ID = ""

        url = build_oauth_url("state_abc")

        self.assertIn("discord.com", url)
        self.assertIn("oauth2/authorize", url)
        self.assertIn("client_id=client_123", url)
        self.assertIn("state=state_abc", url)
        self.assertIn("scope=identify", url)
        self.assertIn("response_type=code", url)


# ---------------------------------------------------------------------------
# Services - desired_role_for_plan
# ---------------------------------------------------------------------------


class DesiredRoleForPlanTest(TestCase):
    """Testes de desired_role_for_plan."""

    @patch("discord_integration.services.settings")
    def test_retorna_role_basic_para_plano_basic(self, mock_settings):
        mock_settings.DISCORD_CLIENT_ID = ""
        mock_settings.DISCORD_CLIENT_SECRET = ""
        mock_settings.DISCORD_REDIRECT_URI = ""
        mock_settings.DISCORD_BOT_TOKEN = ""
        mock_settings.DISCORD_GUILD_ID = ""
        mock_settings.DISCORD_ROLE_BASIC_ID = "role_basic_123"
        mock_settings.DISCORD_ROLE_PREMIUM_ID = "role_premium_456"
        mock_settings.DISCORD_ROLE_PREMIUM_PLUS_ID = "role_pp_789"

        result = desired_role_for_plan(Plan.BASIC)
        self.assertEqual(result, "role_basic_123")

    @patch("discord_integration.services.settings")
    def test_retorna_role_premium_para_plano_premium(self, mock_settings):
        mock_settings.DISCORD_CLIENT_ID = ""
        mock_settings.DISCORD_CLIENT_SECRET = ""
        mock_settings.DISCORD_REDIRECT_URI = ""
        mock_settings.DISCORD_BOT_TOKEN = ""
        mock_settings.DISCORD_GUILD_ID = ""
        mock_settings.DISCORD_ROLE_BASIC_ID = "role_basic_123"
        mock_settings.DISCORD_ROLE_PREMIUM_ID = "role_premium_456"
        mock_settings.DISCORD_ROLE_PREMIUM_PLUS_ID = "role_pp_789"

        result = desired_role_for_plan(Plan.PREMIUM)
        self.assertEqual(result, "role_premium_456")

    @patch("discord_integration.services.settings")
    def test_retorna_role_premium_plus_para_plano_premium_plus(self, mock_settings):
        mock_settings.DISCORD_CLIENT_ID = ""
        mock_settings.DISCORD_CLIENT_SECRET = ""
        mock_settings.DISCORD_REDIRECT_URI = ""
        mock_settings.DISCORD_BOT_TOKEN = ""
        mock_settings.DISCORD_GUILD_ID = ""
        mock_settings.DISCORD_ROLE_BASIC_ID = "role_basic_123"
        mock_settings.DISCORD_ROLE_PREMIUM_ID = "role_premium_456"
        mock_settings.DISCORD_ROLE_PREMIUM_PLUS_ID = "role_pp_789"

        result = desired_role_for_plan(Plan.PREMIUM_PLUS)
        self.assertEqual(result, "role_pp_789")

    @patch("discord_integration.services.settings")
    def test_retorna_none_para_plano_free(self, mock_settings):
        mock_settings.DISCORD_CLIENT_ID = ""
        mock_settings.DISCORD_CLIENT_SECRET = ""
        mock_settings.DISCORD_REDIRECT_URI = ""
        mock_settings.DISCORD_BOT_TOKEN = ""
        mock_settings.DISCORD_GUILD_ID = ""
        mock_settings.DISCORD_ROLE_BASIC_ID = "role_basic_123"
        mock_settings.DISCORD_ROLE_PREMIUM_ID = "role_premium_456"
        mock_settings.DISCORD_ROLE_PREMIUM_PLUS_ID = "role_pp_789"

        result = desired_role_for_plan(Plan.FREE)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Services - sync_profile_roles
# ---------------------------------------------------------------------------


class SyncProfileRolesTest(TestCase):
    """Testes de sync_profile_roles."""

    def setUp(self):
        self.user = create_user()
        self.profile = create_profile(self.user, plan=Plan.PREMIUM)
        self.profile.discord_user_id = "discord_123"
        self.profile.save()

    @patch("discord_integration.services.add_role")
    @patch("discord_integration.services.remove_role")
    @patch("discord_integration.services.fetch_member_roles")
    def test_adiciona_role_quando_premium_e_nao_tem(self, mock_fetch, mock_remove, mock_add):
        mock_fetch.return_value = []
        mock_add.return_value = None
        mock_remove.return_value = None

        with patch("discord_integration.services.settings") as mock_settings:
            mock_settings.DISCORD_CLIENT_ID = ""
            mock_settings.DISCORD_CLIENT_SECRET = ""
            mock_settings.DISCORD_REDIRECT_URI = ""
            mock_settings.DISCORD_BOT_TOKEN = "token"
            mock_settings.DISCORD_GUILD_ID = "guild"
            mock_settings.DISCORD_ROLE_BASIC_ID = "role_basic"
            mock_settings.DISCORD_ROLE_PREMIUM_ID = "role_premium"
            mock_settings.DISCORD_ROLE_PREMIUM_PLUS_ID = "role_pp"

            sync_profile_roles(self.profile)

        mock_add.assert_called_with("discord_123", "role_premium")

    @patch("discord_integration.services.add_role")
    @patch("discord_integration.services.remove_role")
    @patch("discord_integration.services.fetch_member_roles")
    def test_nao_faz_nada_quando_sem_discord_user_id(self, mock_fetch, mock_remove, mock_add):
        self.profile.discord_user_id = ""
        self.profile.save()

        sync_profile_roles(self.profile)

        mock_fetch.assert_not_called()
        mock_add.assert_not_called()


# ---------------------------------------------------------------------------
# Views - DiscordLoginView
# ---------------------------------------------------------------------------


class DiscordLoginViewTest(TestCase):
    """Testes da DiscordLoginView."""

    def setUp(self):
        self.user = create_user()

    def test_anonimo_redireciona_para_login(self):
        response = self.client.get(reverse("discord:login"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    @override_settings(
        DISCORD_CLIENT_ID="client",
        DISCORD_CLIENT_SECRET="secret",
        DISCORD_REDIRECT_URI="https://example.com/callback",
    )
    @patch("discord_integration.views.build_oauth_url")
    def test_autenticado_redireciona_para_discord_oauth(self, mock_build):
        mock_build.return_value = "https://discord.com/oauth2/authorize?state=abc"
        self.client.force_login(self.user)

        response = self.client.get(reverse("discord:login"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("discord.com", response.url)
        mock_build.assert_called_once()

    @override_settings(
        DISCORD_CLIENT_ID="",
        DISCORD_CLIENT_SECRET="",
        DISCORD_REDIRECT_URI="",
    )
    @patch("discord_integration.views.build_oauth_url")
    def test_discord_nao_configurado_redireciona_para_profile(self, mock_build):
        self.client.force_login(self.user)

        response = self.client.get(reverse("discord:login"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:profile"))
        mock_build.assert_not_called()


# ---------------------------------------------------------------------------
# Views - DiscordCallbackView
# ---------------------------------------------------------------------------


class DiscordCallbackViewTest(TestCase):
    """Testes da DiscordCallbackView."""

    def setUp(self):
        self.user = create_user()
        self.profile = self.user.profile

    def test_anonimo_redireciona_para_login(self):
        response = self.client.get(reverse("discord:callback") + "?state=abc&code=xyz")
        self.assertEqual(response.status_code, 302)

    def test_state_invalido_redireciona_para_profile(self):
        self.client.force_login(self.user)
        session = self.client.session
        session["discord_oauth_state"] = "expected_state"
        session.save()

        response = self.client.get(reverse("discord:callback") + "?state=wrong_state&code=xyz")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:profile"))

    def test_sem_code_redireciona_para_profile(self):
        self.client.force_login(self.user)
        session = self.client.session
        session["discord_oauth_state"] = "expected_state"
        session.save()

        response = self.client.get(reverse("discord:callback") + "?state=expected_state")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:profile"))

    @patch("discord_integration.views.fetch_discord_user")
    @patch("discord_integration.views.exchange_code_for_token")
    def test_callback_valido_salva_discord_no_perfil(self, mock_exchange, mock_fetch):
        mock_exchange.return_value = {"access_token": "token"}
        mock_fetch.return_value = {
            "id": "discord_123",
            "username": "testuser",
            "discriminator": "0",
        }
        self.client.force_login(self.user)
        session = self.client.session
        session["discord_oauth_state"] = "expected_state"
        session.save()

        with patch("discord_integration.views.sync_user_roles"):
            response = self.client.get(
                reverse("discord:callback") + "?state=expected_state&code=valid_code"
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:profile"))

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.discord_user_id, "discord_123")
        self.assertEqual(self.profile.discord_username, "testuser")


# ---------------------------------------------------------------------------
# Views - DiscordUnlinkView
# ---------------------------------------------------------------------------


class DiscordUnlinkViewTest(TestCase):
    """Testes da DiscordUnlinkView."""

    def setUp(self):
        self.user = create_user()
        self.profile = create_profile(self.user)
        self.profile.discord_user_id = "discord_456"
        self.profile.discord_username = "discorduser"
        self.profile.save()

    def test_anonimo_redireciona_para_login(self):
        response = self.client.post(reverse("discord:unlink"))
        self.assertEqual(response.status_code, 302)

    def test_unlink_remove_discord_do_perfil(self):
        self.client.force_login(self.user)

        with patch("discord_integration.views.remove_all_roles"):
            with patch("discord_integration.views.sync_user_roles"):
                response = self.client.post(reverse("discord:unlink"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:profile"))

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.discord_user_id, "")
        self.assertEqual(self.profile.discord_username, "")
        self.assertIsNone(self.profile.discord_connected_at)

    def test_unlink_sem_discord_vinculado_retorna_warning(self):
        self.profile.discord_user_id = ""
        self.profile.save()
        self.client.force_login(self.user)

        response = self.client.post(reverse("discord:unlink"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:profile"))


# ---------------------------------------------------------------------------
# Views - DiscordCallbackView: vínculo duplicado e resposta sem id (A6, A12)
# ---------------------------------------------------------------------------


class DiscordCallbackVinculoDuplicadoTest(TestCase):
    """
    Regressão de A6.

    Duas contas no mesmo Discord se anulavam na sincronização das 04:00: uma
    adicionava a role, a outra removia. O callback agora recusa o vínculo.
    """

    def setUp(self):
        self.dono = create_user(email="dono@example.com")
        dono_profile = self.dono.profile
        dono_profile.discord_user_id = "discord_123"
        dono_profile.discord_username = "dono"
        dono_profile.save()

        self.intruso = create_user(email="intruso@example.com")

    def _callback(self, user_data):
        self.client.force_login(self.intruso)
        session = self.client.session
        session["discord_oauth_state"] = "expected_state"
        session.save()

        with (
            patch("discord_integration.views.exchange_code_for_token") as mock_exchange,
            patch("discord_integration.views.fetch_discord_user") as mock_fetch,
            patch("discord_integration.views.sync_user_roles") as mock_task,
        ):
            mock_exchange.return_value = {"access_token": "token"}
            mock_fetch.return_value = user_data
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.get(
                    reverse("discord:callback") + "?state=expected_state&code=valid_code"
                )
        return response, mock_task

    def test_discord_ja_vinculado_em_outra_conta_e_recusado(self):
        response, mock_task = self._callback(
            {"id": "discord_123", "username": "intruso", "discriminator": "0"}
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:profile"))

        self.intruso.profile.refresh_from_db()
        self.assertEqual(self.intruso.profile.discord_user_id, "")
        self.assertIsNone(self.intruso.profile.discord_connected_at)
        mock_task.delay.assert_not_called()

    def test_dono_do_vinculo_continua_intacto(self):
        self._callback({"id": "discord_123", "username": "intruso", "discriminator": "0"})

        self.dono.profile.refresh_from_db()
        self.assertEqual(self.dono.profile.discord_user_id, "discord_123")
        self.assertEqual(self.dono.profile.discord_username, "dono")

    def test_revincular_o_mesmo_discord_na_propria_conta_funciona(self):
        """A checagem não pode impedir o usuário de reconectar a si mesmo."""
        self.client.force_login(self.dono)
        session = self.client.session
        session["discord_oauth_state"] = "expected_state"
        session.save()

        with (
            patch("discord_integration.views.exchange_code_for_token") as mock_exchange,
            patch("discord_integration.views.fetch_discord_user") as mock_fetch,
            patch("discord_integration.views.sync_user_roles"),
        ):
            mock_exchange.return_value = {"access_token": "token"}
            mock_fetch.return_value = {
                "id": "discord_123",
                "username": "dono_novo_nick",
                "discriminator": "0",
            }
            response = self.client.get(
                reverse("discord:callback") + "?state=expected_state&code=valid_code"
            )

        self.assertEqual(response.status_code, 302)
        self.dono.profile.refresh_from_db()
        self.assertEqual(self.dono.profile.discord_username, "dono_novo_nick")

    def test_resposta_sem_id_nao_grava_perfil_conectado(self):
        """A12: `get("id", "")` deixava o perfil 'conectado' a ninguém."""
        response, mock_task = self._callback({"username": "sem_id", "discriminator": "0"})

        self.assertEqual(response.status_code, 302)
        self.intruso.profile.refresh_from_db()
        self.assertEqual(self.intruso.profile.discord_user_id, "")
        self.assertIsNone(self.intruso.profile.discord_connected_at)
        mock_task.delay.assert_not_called()


# ---------------------------------------------------------------------------
# _bot_request: teto de tentativas e de espera em 429 (A4, A9)
# ---------------------------------------------------------------------------


def _resposta(status_code: int, payload: dict | None = None):
    resp = Mock()
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 300
    resp.json.return_value = payload if payload is not None else {}
    resp.text = ""
    return resp


@patch("discord_integration.services._bot_headers", return_value={})
class BotRequestRateLimitTest(TestCase):
    """
    Regressão de A4/A9.

    Era um `while True` dormindo o `retry_after` do Discord sem teto. No
    callback OAuth isso segurava um worker do gunicorn; no worker `--pool=solo`,
    segurava a coleta macro junto.
    """

    def setUp(self):
        # `_discord_rate_limiter` é singleton de módulo: sem zerar, as chamadas
        # de um teste contam no limite de 10/s do seguinte e ele dorme sozinho.
        _discord_rate_limiter._calls.clear()

    @patch("discord_integration.services.time.sleep")
    @patch("discord_integration.services.requests.request")
    def test_desiste_depois_de_tres_tentativas(self, mock_request, mock_sleep, _headers):
        mock_request.return_value = _resposta(429, {"retry_after": 30})

        with self.assertRaises(DiscordRateLimited):
            _bot_request("GET", "https://discord.com/api/teste")

        self.assertEqual(mock_request.call_count, MAX_TENTATIVAS_429)

    @patch("discord_integration.services.time.sleep")
    @patch("discord_integration.services.requests.request")
    def test_espera_e_limitada_mesmo_com_retry_after_alto(self, mock_request, mock_sleep, _headers):
        """O Discord manda 30-60s em rate limit de guilda; dormir isso era o bug."""
        mock_request.return_value = _resposta(429, {"retry_after": 300})

        with self.assertRaises(DiscordRateLimited):
            _bot_request("GET", "https://discord.com/api/teste")

        esperas = [chamada.args[0] for chamada in mock_sleep.call_args_list]
        self.assertTrue(esperas)
        for espera in esperas:
            self.assertLessEqual(espera, MAX_ESPERA_429_SEGUNDOS)

    @patch("discord_integration.services.time.sleep")
    @patch("discord_integration.services.requests.request")
    def test_429_seguido_de_sucesso_retorna_a_resposta(self, mock_request, mock_sleep, _headers):
        mock_request.side_effect = [_resposta(429, {"retry_after": 1}), _resposta(200)]

        resp = _bot_request("GET", "https://discord.com/api/teste")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(mock_request.call_count, 2)

    @patch("discord_integration.services.time.sleep")
    @patch("discord_integration.services.requests.request")
    def test_resposta_normal_nao_dorme(self, mock_request, mock_sleep, _headers):
        mock_request.return_value = _resposta(200)

        _bot_request("GET", "https://discord.com/api/teste")

        mock_sleep.assert_not_called()

    @patch("discord_integration.services.time.sleep")
    @patch("discord_integration.services.requests.request")
    def test_corpo_ilegivel_no_429_nao_quebra(self, mock_request, mock_sleep, _headers):
        resp_429 = _resposta(429)
        resp_429.json.side_effect = ValueError("resposta sem JSON")
        mock_request.side_effect = [resp_429, _resposta(200)]

        resp = _bot_request("GET", "https://discord.com/api/teste")

        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# Callback OAuth: nada de Discord dentro do request (A4, A12)
# ---------------------------------------------------------------------------


class DiscordCallbackForaDoRequestTest(TestCase):
    """
    Regressão de A4.

    O callback chamava `sync_profile_roles()` síncrono (até 4 requisições de 20s
    ao Discord) e, logo depois, enfileirava o mesmo trabalho.
    """

    def setUp(self):
        self.user = create_user()

    def _callback(self, executar_on_commit=True):
        self.client.force_login(self.user)
        session = self.client.session
        session["discord_oauth_state"] = "expected_state"
        session.save()

        with (
            patch("discord_integration.views.exchange_code_for_token") as mock_exchange,
            patch("discord_integration.views.fetch_discord_user") as mock_fetch,
            patch("discord_integration.views.sync_user_roles") as mock_task,
        ):
            mock_exchange.return_value = {"access_token": "token"}
            mock_fetch.return_value = {
                "id": "discord_777",
                "username": "usuario",
                "discriminator": "0",
            }
            with self.captureOnCommitCallbacks(execute=executar_on_commit):
                response = self.client.get(
                    reverse("discord:callback") + "?state=expected_state&code=valid_code"
                )
        return response, mock_task

    def test_nao_fala_com_o_discord_dentro_do_request(self):
        with patch("discord_integration.services._bot_request") as mock_bot:
            response, _ = self._callback()

        self.assertEqual(response.status_code, 302)
        mock_bot.assert_not_called()

    def test_enfileira_a_sincronizacao_uma_unica_vez(self):
        _, mock_task = self._callback()

        mock_task.delay.assert_called_once_with(self.user.id)

    def test_enfileira_so_depois_do_commit(self):
        """P6 de novo: `.delay()` dentro da transação faz o worker ler estado antigo."""
        _, mock_task = self._callback(executar_on_commit=False)

        mock_task.delay.assert_not_called()

    def test_broker_fora_nao_derruba_a_vinculacao(self):
        self.client.force_login(self.user)
        session = self.client.session
        session["discord_oauth_state"] = "expected_state"
        session.save()

        with (
            patch("discord_integration.views.exchange_code_for_token") as mock_exchange,
            patch("discord_integration.views.fetch_discord_user") as mock_fetch,
            patch("discord_integration.views.sync_user_roles") as mock_task,
        ):
            mock_exchange.return_value = {"access_token": "token"}
            mock_fetch.return_value = {"id": "discord_778", "username": "u", "discriminator": "0"}
            mock_task.delay.side_effect = OSError("broker fora")
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.get(
                    reverse("discord:callback") + "?state=expected_state&code=valid_code"
                )

        self.assertEqual(response.status_code, 302)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.discord_user_id, "discord_778")

    def test_state_e_removido_da_sessao(self):
        """A12: mantido na sessão, um callback antigo seguia válido."""
        self._callback()

        self.assertNotIn("discord_oauth_state", self.client.session)

    def test_state_nao_serve_duas_vezes(self):
        self._callback()

        response = self.client.get(
            reverse("discord:callback") + "?state=expected_state&code=outro_code"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:profile"))


# ---------------------------------------------------------------------------
# Filas separadas (A9)
# ---------------------------------------------------------------------------


class RoteamentoDeFilasTest(TestCase):
    """
    Regressão de A9.

    Com uma fila só e `--pool=solo`, a sincronização das 04:00 e a coleta macro
    disputavam o mesmo processo: o painel parava de atualizar durante a sync.
    """

    def _fila(self, nome_da_task: str) -> str:
        destino = celery_app.amqp.router.route({}, nome_da_task)["queue"]
        return getattr(destino, "name", destino)

    def test_discord_vai_para_a_fila_interativa(self):
        self.assertEqual(
            self._fila("discord_integration.tasks.sync_all_discord_roles"), "interativo"
        )
        self.assertEqual(self._fila("discord_integration.tasks.sync_user_roles"), "interativo")

    def test_coleta_macro_vai_para_a_fila_macro(self):
        self.assertEqual(self._fila("macro.tasks.collect_macro_cycle"), "macro")

    def test_email_de_recuperacao_nao_espera_a_coleta(self):
        self.assertEqual(self._fila("accounts.tasks.send_password_reset_email"), "interativo")

    def test_task_nao_roteada_continua_na_fila_padrao(self):
        """Nada some se uma task nova não for listada em CELERY_TASK_ROUTES."""
        self.assertEqual(self._fila("payments.tasks.qualquer_coisa"), "celery")
