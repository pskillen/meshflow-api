import base64

from django.conf import settings
from django.http import HttpResponse


class MetricsAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/metrics":
            auth = request.META.get("HTTP_AUTHORIZATION")
            expected_user = "prometheus"
            expected_pass = settings.PROMETHEUS_PASSWORD
            expected = "Basic " + base64.b64encode(f"{expected_user}:{expected_pass}".encode()).decode()

            if auth != expected:
                response = HttpResponse("Unauthorized", status=401)
                response["WWW-Authenticate"] = 'Basic realm="Metrics"'
                return response

        return self.get_response(request)
