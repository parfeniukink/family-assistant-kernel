from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)
from starlette.requests import Request
from starlette.responses import Response

from src.config import settings

# NOTE: For more information:
#       fastapi.middleware.cors.CORSMiddleware
FASTAPI_CORS_MIDDLEWARE_OPTIONS: dict = {
    "allow_origins": settings.cors.allow_origins,
    "allow_credentials": settings.cors.allow_credentials,
    "allow_methods": settings.cors.allow_methods,
    "allow_headers": settings.cors.allow_headers,
    "expose_headers": settings.cors.expose_headers,
    "max_age": settings.cors.max_age,
}

_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'none'",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
    "Cache-Control": "no-store",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware that adds security headers to every HTTP response.
    Suitable for a JSON-only API behind an SSL-terminating ingress.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)

        for header, value in _SECURITY_HEADERS.items():
            response.headers[header] = value

        return response
