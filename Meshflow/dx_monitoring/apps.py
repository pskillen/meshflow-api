from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class DxMonitoringConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dx_monitoring"
    label = "dx_monitoring"
    verbose_name = _("DX Monitoring")

    def ready(self):
        import dx_monitoring.receivers  # noqa: F401

        from . import signals  # noqa: F401
