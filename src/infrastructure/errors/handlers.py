"""
module with fastapi error handlers
that are dispatched automatically by fastapi engine.


todo:
 - [ ] add handler for invalid `Literal` query parameters
"""

import sentry_sdk
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from slowapi.errors import RateLimitExceeded
from starlette import status
from starlette.requests import Request

from src.config import settings

from ..responses import (
    ErrorDetail,
    ErrorResponse,
    ErrorResponseMulti,
    ErrorType,
)
from .exceptions import AuthenticationError, BaseError


def sentry_error_traceback(error: BaseException):
    if settings.sentry_dsn:
        sentry_sdk.capture_exception(error)


def fastapi_to_internal_error_mapper(value: str) -> ErrorType:
    """maps ValidationError, HTTPException, other exceptions occured
    in the runtime to internal error types.

    notes:
        ``internal`` stand for overall internal error. aka Exception in Python
        ``external`` stand for external API/Service issue
        ``missing`` some data is missed
        ``bad-type`` some fields has wrong data types
    """

    if value == "missing":
        return "missing"
    elif "_type" in value:
        return "bad-type"
    else:
        return "internal"


def unprocessable_entity_error_handler(
    _: Request, error: RequestValidationError
) -> JSONResponse:
    """This function is called if the request validation is not passed.
    This error is raised automatically by FastAPI.
    """

    logger.error(error)
    response = ErrorResponseMulti(
        result=[
            ErrorResponse(
                message=err["msg"],
                detail=ErrorDetail(
                    path=err["loc"],
                    type=fastapi_to_internal_error_mapper(err["type"]),
                ),
            )
            for err in error.errors()
        ]
    )
    sentry_error_traceback(error)

    return JSONResponse(
        content=jsonable_encoder(response.model_dump(by_alias=True)),
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


def value_error_handler(_: Request, error: ValueError) -> JSONResponse:
    logger.error(error)
    response = ErrorResponse(message=str(error))
    sentry_error_traceback(error)

    return JSONResponse(
        content=jsonable_encoder(response.model_dump(by_alias=True)),
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


def fastapi_http_exception_handler(
    _: Request, error: HTTPException
) -> JSONResponse:
    """This function is called if the HTTPException was raised."""

    logger.error(error)
    response = ErrorResponse(message=error.detail)
    sentry_error_traceback(error)
    return JSONResponse(
        content=response.model_dump(by_alias=True),
        status_code=error.status_code,
    )


def not_implemented_error_handler(
    _: Request, error: NotImplementedError
) -> JSONResponse:
    """This function is called if the NotImplementedError was raised."""

    logger.error(error)
    response = ErrorResponse(message=str(error) or "⚠️ Work in progress")
    sentry_error_traceback(error)

    return JSONResponse(
        content=response.model_dump(by_alias=True),
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
    )


def database_error_handler(
    _: Request, error: NotImplementedError
) -> JSONResponse:
    """This function is called if the NotImplementedError was raised."""

    logger.error(error)
    response = ErrorResponse(message="Database error occurred")
    sentry_error_traceback(error)

    return JSONResponse(
        content=response.model_dump(by_alias=True),
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def authentication_error(
    _: Request | None, error: AuthenticationError
) -> JSONResponse:

    logger.error(error)
    response = ErrorResponse(message=str(error))
    sentry_error_traceback(error)

    return JSONResponse(
        response.model_dump(by_alias=True),
        status_code=status.HTTP_401_UNAUTHORIZED,
    )


def base_error_handler(_: Request, error: BaseError) -> JSONResponse:
    """This function handles all errors that are inherited from BaseError.
    Each class that inherits the BaseError has a status_code attribute.
    """

    logger.error(error)
    response = ErrorResponse(message=str(error))
    sentry_error_traceback(error)

    return JSONResponse(
        response.model_dump(by_alias=True),
        status_code=error.status_code,
    )


def unhandled_error_handler(_: Request, error: Exception) -> JSONResponse:
    logger.error(error)
    response = ErrorResponse(message=str(error))
    sentry_error_traceback(error)

    return JSONResponse(
        response.model_dump(by_alias=True),
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


async def rate_limit_exceeded_handler(
    _: Request, error: RateLimitExceeded
) -> JSONResponse:
    logger.error(error)
    response = ErrorResponse(
        message="Rate limit exceeded. Try again later.",
    )

    retry_after = "60"
    if error.detail:
        detail_str = str(error.detail)
        if "per minute" in detail_str.lower():
            retry_after = "60"
        elif "per hour" in detail_str.lower():
            retry_after = "3600"

    return JSONResponse(
        content=response.model_dump(by_alias=True),
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        headers={"Retry-After": retry_after},
    )
