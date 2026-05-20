from django.apps import AppConfig


class PacketsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "packets"

    def ready(self):
        """Import signal handlers when Django is ready."""
        import packets.receivers  # noqa
        from packets.traceroute_completion_wiring import connect_auto_traceroute_completed_receivers

        connect_auto_traceroute_completed_receivers()
