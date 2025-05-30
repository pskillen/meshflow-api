from django.apps import AppConfig


class PacketsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "packets"

    def ready(self):
        """Import signal handlers when Django is ready."""
        import packets.receivers  # noqa
