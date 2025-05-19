from django.apps import AppConfig


class WsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ws"

    def ready(self):
        """Import signal handlers when Django is ready."""
        import ws.receivers  # noqa
