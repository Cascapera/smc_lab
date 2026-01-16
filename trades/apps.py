from django.apps import AppConfig


class TradesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "trades"

    def ready(self) -> None:
        import trades.signals  # noqa: F401
