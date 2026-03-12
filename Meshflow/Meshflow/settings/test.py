from .base import *  # noqa

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
