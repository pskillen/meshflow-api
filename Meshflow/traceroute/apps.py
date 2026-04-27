from django.apps import AppConfig


class TracerouteConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "traceroute"
    verbose_name = "Traceroute"

    def ready(self):
        """Import signal handlers when Django is ready."""
        import traceroute.receivers  # noqa: F401
