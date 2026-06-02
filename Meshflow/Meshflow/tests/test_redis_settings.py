"""Redis-related Django settings (Channels + Celery)."""

import os

from django.test import SimpleTestCase


class ChannelRedisHostTest(SimpleTestCase):
    def test_default_socket_timeout_for_channels(self):
        from Meshflow.settings import base as settings_base

        host = settings_base._channel_redis_host()
        self.assertIn("address", host)
        self.assertEqual(host["socket_timeout"], 30.0)
        self.assertEqual(host["socket_connect_timeout"], 5.0)

    def test_socket_timeout_none_omits_key(self):
        from Meshflow.settings import base as settings_base

        prior = os.environ.get("CHANNEL_REDIS_SOCKET_TIMEOUT")
        try:
            os.environ["CHANNEL_REDIS_SOCKET_TIMEOUT"] = "none"
            host = settings_base._channel_redis_host()
            self.assertNotIn("socket_timeout", host)
        finally:
            if prior is None:
                os.environ.pop("CHANNEL_REDIS_SOCKET_TIMEOUT", None)
            else:
                os.environ["CHANNEL_REDIS_SOCKET_TIMEOUT"] = prior

    def test_celery_result_expires_default(self):
        from django.conf import settings

        self.assertEqual(settings.CELERY_RESULT_EXPIRES, 3600)
