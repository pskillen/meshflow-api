from django.apps import AppConfig


class M2MApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "m2m_api"

    def ready(self):
        import m2m_api.signals  # noqa: F401
