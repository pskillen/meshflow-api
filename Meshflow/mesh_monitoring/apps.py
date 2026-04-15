from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class MeshMonitoringConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "mesh_monitoring"
    label = "mesh_monitoring"
    verbose_name = _("Mesh Monitoring")
