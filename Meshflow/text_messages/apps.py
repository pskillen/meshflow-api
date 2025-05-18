from django.apps import AppConfig


class TextMessagesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "text_messages"

    def ready(self):
        """Import signal handlers when Django is ready."""
        import text_messages.receivers  # noqa
