# warehouse/middleware.py
import logging

logger = logging.getLogger(__name__)

class DebugCSRFOriginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.META.get("HTTP_ORIGIN")
        xf_proto = request.META.get("HTTP_X_FORWARDED_PROTO")
        host = request.META.get("HTTP_HOST")
        is_secure = request.is_secure()
        logger.warning(
            "CSRF debug: Origin=%r, X-Forwarded-Proto=%r, Host=%r, is_secure=%s",
            origin, xf_proto, host, is_secure
        )
        return self.get_response(request)
