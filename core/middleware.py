from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from core.views import healthz

HEALTHZ_PATH = "/healthz/"


class HealthCheckMiddleware:
    """Answer ``/healthz/`` before host validation.

    Container healthchecks call ``http://127.0.0.1:8000/healthz/``; serving the
    probe here means ``ALLOWED_HOSTS`` can stay limited to real domains.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path == HEALTHZ_PATH and request.method == "GET":
            return healthz(request)
        return self.get_response(request)
