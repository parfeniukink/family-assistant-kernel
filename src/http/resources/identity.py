from fastapi import APIRouter, Body, Depends, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from src import application as op
from src.application import authentication
from src.config import settings
from src.domain import users as domain
from src.infrastructure import Response

from ..contracts.identity import (
    GetTokensRequestBody,
    RefreshRequestBody,
    TokenPairResponse,
    User,
    UserConfigurationPartialUpdateRequestBody,
)

router = APIRouter(prefix="/identity", tags=["Identity"])

# Rate limiter for auth endpoints
limiter = Limiter(key_func=get_remote_address)

# Rate limit strings
_login_limit = (
    f"{settings.rate_limit.login_per_minute}/minute;"
    f"{settings.rate_limit.login_per_hour}/hour"
)
_refresh_limit = f"{settings.rate_limit.refresh_per_minute}/minute"


@router.post("/tokens")
@limiter.limit(_login_limit)
async def get_tokens(
    request: Request,
    body: GetTokensRequestBody = Body(...),
) -> Response[TokenPairResponse]:
    """Authenticate user with username and password.

    NOTES
    (1) Rate limited to prevent brute force attacks
    """

    token_pair = await authentication.get_tokens_pair(
        body.username, body.password
    )

    return Response[TokenPairResponse](
        result=TokenPairResponse.model_validate(token_pair)
    )


@router.post("/refresh")
@limiter.limit(_refresh_limit)
async def refresh(
    request: Request,
    body: RefreshRequestBody = Body(...),
) -> Response[TokenPairResponse]:
    """Refresh tokens using a valid refresh token.

    NOTES
    (1) Rate limited to prevent abuse
    """

    token_pair = await authentication.refresh_tokens(body.refresh_token)

    return Response[TokenPairResponse](
        result=TokenPairResponse.model_validate(token_pair)
    )


@router.post("/revoke-refresh", status_code=status.HTTP_204_NO_CONTENT)
async def logout() -> None:
    """Logout by revoking the refresh token."""

    # TODO: Remove refresh tokens from the cache

    return None


@router.get("/users")
async def user_retrieve(
    user: domain.User = Depends(op.authorize),
) -> Response[User]:
    """retrieve current user information information."""

    return Response[User](result=User.from_instance(user))


@router.patch("/users/configuration")
async def parial_update_user_configuration(
    user: domain.User = Depends(op.authorize),
    body: UserConfigurationPartialUpdateRequestBody = Body(...),
) -> Response[User]:
    """update the user configuration partially."""

    instance: domain.User = await op.update_user_configuration(
        user, **body.model_dump(exclude_unset=True)
    )

    return Response[User](result=User.from_instance(instance))
