from .base import *  # noqa

# Tests use locmem cache so pytest does not require Redis for django.core.cache
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "meshflow-test-cache",
    },
}

# Use in-memory channel layer for testing (no Redis required)
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

# Use SQLite for testing
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Disable password hashing for faster tests
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Disable logging during tests
LOGGING = {}

# Disable CORS for tests
CORS_ALLOWED_ORIGINS = []
CORS_ALLOW_CREDENTIALS = False

# Run Celery tasks synchronously in tests so `.delay()` invokes the task in-process.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
