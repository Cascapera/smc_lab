"""
Testes do app discord_integration - OAuth, services e views.
"""

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Plan
from accounts.tests import create_profile, create_user

from .services import build_oauth_url, desired_role_for_plan, sync_profile_roles

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

    @patch("discord_integration.views.sync_profile_roles")
    @patch("discord_integration.views.fetch_discord_user")
    @patch("discord_integration.views.exchange_code_for_token")
    def test_callback_valido_salva_discord_no_perfil(self, mock_exchange, mock_fetch, mock_sync):
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
