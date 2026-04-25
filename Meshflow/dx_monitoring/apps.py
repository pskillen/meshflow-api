from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class DxMonitoringConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dx_monitoring"
    label = "dx_monitoring"
    verbose_name = _("DX Monitoring")
