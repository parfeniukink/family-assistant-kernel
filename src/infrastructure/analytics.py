"""Request analytics middleware.

Logs every incoming HTTP request to PostgreSQL for monitoring
and security auditing. The DB write is fire-and-forget to avoid
adding latency to request processing.
"""

import asyncio
import time

import jwt
from loguru import logger
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)
from starlette.requests import Request
from starlette.responses import Response

from src.config import settings
from src.infrastructure.database.session import session_factoy
from src.infrastructure.database.tables import HTTPRequestLog


def _extract_client_ip(request: Request) -> str:
    """Extract real client IP from proxy headers.

    Priority: X-Real-IP > X-Forwarded-For (first entry)
    > request.client.host.

    nginx-ingress on K3S sets X-Real-IP and X-Forwarded-For.
    """

    if real_ip := request.headers.get("x-real-ip"):
        return real_ip.strip()

    if forwarded_for := request.headers.get("x-forwarded-for"):
        return forwarded_for.split(",")[0].strip()

    if request.client:
        return request.client.host

    return "unknown"


def _extract_user_id(request: Request) -> int | None:
    """Best-effort extraction of user_id from JWT.

    Never raises - returns None on any failure.
    """

    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]

    try:
        payload = jwt.decode(
            token,
            settings.auth.secret_key,
            algorithms=[settings.auth.algorithm],
        )
        sub = payload.get("sub")
        return int(sub) if sub is not None else None
    except Exception:
        return None


async def _persist_request_log(
    ip_address: str,
    method: str,
    path: str,
    status_code: int,
    user_agent: str,
    referer: str | None,
    country: str | None,
    city: str | None,
    user_id: int | None,
    duration_ms: int,
    content_length: int | None,
) -> None:
    """Write a request log row to PostgreSQL.

    This is called as a fire-and-forget task. Errors are
    caught and logged, never propagated.
    """

    try:
        session = session_factoy()
        try:
            log_entry = HTTPRequestLog(
                ip_address=ip_address,
                method=method,
                path=path,
                status_code=status_code,
                user_agent=user_agent,
                referer=referer,
                country=country,
                city=city,
                user_id=user_id,
                duration_ms=duration_ms,
                content_length=content_length,
            )
            session.add(log_entry)
            await session.commit()
        finally:
            await session.close()
    except Exception as error:
        logger.warning(f"Failed to persist request log: {error}")


class RequestAnalyticsMiddleware(BaseHTTPMiddleware):
    """Middleware that logs HTTP request metadata to
    PostgreSQL for analytics and security auditing.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.monotonic()

        response = await call_next(request)

        duration_ms = int((time.monotonic() - start) * 1000)

        ip_address = _extract_client_ip(request)
        user_agent = request.headers.get("user-agent", "")[:500]
        referer = request.headers.get("referer")
        country = request.headers.get("x-geoip-country")
        city = request.headers.get("x-geoip-city")
        user_id = _extract_user_id(request)

        raw_length = request.headers.get("content-length")
        content_length: int | None = None
        if raw_length is not None:
            try:
                content_length = int(raw_length)
            except ValueError:
                pass

        asyncio.create_task(
            _persist_request_log(
                ip_address=ip_address,
                method=request.method,
                path=request.url.path[:500],
                status_code=response.status_code,
                user_agent=user_agent,
                referer=referer,
                country=country,
                city=city,
                user_id=user_id,
                duration_ms=duration_ms,
                content_length=content_length,
            )
        )

        return response
