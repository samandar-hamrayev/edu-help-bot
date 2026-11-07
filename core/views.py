import logging

from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@require_GET
def healthz(request: HttpRequest) -> JsonResponse:
    """Liveness + DB readiness probe used by Docker/nginx healthchecks."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        logger.exception("Health check: database unavailable")
        return JsonResponse({"status": "error", "database": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
