"""
this file is an application entrypoint.
the overall structure is inspired by DDD (Eric Evans):
    ↓ main (entrypoint)
    ↓ http (presentation tier)
        ↓ resources (endpoints)
        ↓ contracts (data structures)
    ↓ operational (application tier)
    ↓ domain (business model tier)
    ↓ integrations (infrastructure tier)
        ↓ openai
        ↓ monobank
        ↓ privatbank
    ↓ infrastructure (infrastructure tier)
        ↓ database (ORM, tables)
        ↓ config (global configuration)

the main purpose of the application is working with TRANSACTIONS (costs,
incomes, exchanges). to claim analytics based on that information.

so the overall workflow would look next:
1. client save the income transaction
2. client save the cost transaction
3. client claim for analytics (based on previously saved transactions)
    to check the financial state

also, the equity and all the transactions are shared to all users in the system
so each of them can see the transactions themselves, analytics and equity.
on the other hand user settings are not sharable for others.
"""

import sentry_sdk
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.loguru import LoguruIntegration
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src import http
from src.config import settings
from src.infrastructure import errors, factories, hooks, middleware
from src.infrastructure.analytics import RequestAnalyticsMiddleware
from src.infrastructure.middleware import SecurityHeadersMiddleware

logger.add(
    settings.logging.file,
    format=settings.logging.format,
    rotation=settings.logging.rotation,
    compression=settings.logging.compression,
    level=settings.logging.level,
)


exception_handlers = (
    {
        ValueError: errors.value_error_handler,
        RequestValidationError: errors.unprocessable_entity_error_handler,
        HTTPException: errors.fastapi_http_exception_handler,
        NotImplementedError: errors.not_implemented_error_handler,
        RateLimitExceeded: errors.rate_limit_exceeded_handler,
        errors.BaseError: errors.base_error_handler,
        Exception: errors.unhandled_error_handler,
    }
    if settings.debug is False
    else {}
)

middlewares: list[tuple] = []

if settings.sentry_dsn and settings.debug is False:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        # add data like request headers and IP for users
        # https://docs.sentry.io/platforms/python/data-management/data-collected/
        send_default_pii=True,
        # 1.0 to capture 100% of transactions for tracing
        traces_sample_rate=0.1,
        # 1.0 to profile 100% of profile sessions
        profile_session_sample_rate=0.5,
        # "trace" to automatically run the profiler
        # on when there is an active transaction
        profile_lifecycle="trace",
        attach_stacktrace=True,
        environment="development" if settings.debug else "production",
        integrations=[
            FastApiIntegration(),
            LoguruIntegration(),
        ],
        _experiments={
            "enable_logs": True,
        },
    )

    middlewares.append((SentryAsgiMiddleware, {}))

    logger.success("Sentry initialized")

if settings.debug is False:
    middlewares.extend(
        [
            (RequestAnalyticsMiddleware, {}),
            (CORSMiddleware, middleware.FASTAPI_CORS_MIDDLEWARE_OPTIONS),
            (SecurityHeadersMiddleware, {}),
        ]
    )


app: FastAPI = factories.asgi_app(
    debug=settings.debug,
    rest_routers=(
        http.users_router,
        http.currencies_router,
        http.analytics_router,
        http.transactions_router,
        http.costs_router,
        http.incomes_router,
        http.exchange_router,
        http.notifications_router,
    ),
    middlewares=middlewares,
    exception_handlers=exception_handlers,
    lifespan=hooks.lifespan_event,
)

app.state.limiter = Limiter(key_func=get_remote_address)
