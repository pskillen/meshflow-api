import os

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

# SQLite in memory by default. Set TEST_DB_ENGINE=postgres to run the suite on PostgreSQL (what prod runs);
# connection comes from POSTGRES_DB/USER/PASSWORD/HOST/PORT, as in base.py. CI runs both.
if os.environ.get("TEST_DB_ENGINE", "sqlite").lower() in ("postgres", "postgresql"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB", "meshflow"),
            "USER": os.environ.get("POSTGRES_USER", "meshflow"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "meshflow"),
            "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        }
    }
else:
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
