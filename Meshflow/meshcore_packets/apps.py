from django.apps import AppConfig


class MeshcorePacketsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "meshcore_packets"
    verbose_name = "MeshCore packets"

    def ready(self):
        import meshcore_packets.receivers  # noqa: F401
