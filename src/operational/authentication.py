"""
Authentication operational layer.
"""

import time

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger

from src import domain
from src.infrastructure import InternalData, database, errors, security

http_bearer = HTTPBearer(auto_error=False)


class TokensPair(InternalData):
    access_token: str
    refresh_token: str


async def authorize(
    creds: HTTPAuthorizationCredentials | None = Depends(http_bearer),
) -> domain.users.User:
    """Dependency-injection for FastAPI."""

    if creds is None:
        return errors.authentication_error(  # type: ignore
            None,
            errors.AuthenticationError(
                "Authorization HTTP header is not specified"
            ),
        )

    token = creds.credentials

    try:
        payload = security.decode_token(token)
        if payload.get("type") != "access":
            return errors.authentication_error(  # type: ignore
                None, errors.AuthenticationError("Invalid token type")
            )
        user_id = int(payload["sub"])
    except jwt.ExpiredSignatureError:
        return errors.authentication_error(  # type: ignore
            None, errors.AuthenticationError("Token expired")
        )
    except (jwt.InvalidTokenError, KeyError, ValueError) as error:
        logger.error(error)
        return errors.authentication_error(  # type: ignore
            None, errors.AuthenticationError("Invalid token")
        )
    else:
        try:
            user = await domain.users.UserRepository().user_by_id(user_id)
        except Exception as error:
            logger.error(error)
            return errors.authentication_error(  # type: ignore
                None, errors.AuthenticationError("Invlid credentials")
            )
        else:
            return domain.users.User.from_instance(user)


async def get_tokens_pair(username: str, password: str) -> TokensPair:
    """Authenticate user and return token pair."""

    try:
        user: database.User = await domain.users.UserRepository().user_by_name(
            username
        )
    except errors.NotFoundError:
        return errors.authentication_error(  # type: ignore
            None, errors.AuthenticationError("Invalid credentials")
        )
    else:
        # Verify password
        if not user.password_hash:
            return errors.authentication_error(  # type: ignore
                None, errors.AuthenticationError("Invalid credentials")
            )

        if not security.verify_password(password, user.password_hash):
            return errors.authentication_error(  # type: ignore
                None, errors.AuthenticationError("Invalid credentials")
            )

        # Create tokens
        access_token = security.create_access_token(user.id)
        refresh_token = security.create_refresh_token(user.id)

        # TODO: Store refresh token hash in cache
        # token_hash = security.hash_refresh_token(refresh_token)

        return TokensPair(
            access_token=access_token,
            refresh_token=refresh_token,
        )


async def refresh_tokens(refresh_token: str) -> TokensPair:
    """Returns new TokenPair with fresh access token and same refresh token."""

    try:
        # Decode and validate the refresh token
        payload = security.decode_token(refresh_token)
    except jwt.ExpiredSignatureError:
        return errors.authentication_error(  # type: ignore
            None, errors.AuthenticationError("Refresh token expired")
        )
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return errors.authentication_error(  # type: ignore
            None, errors.AuthenticationError("Refresh token invalid")
        )
    else:
        if (exp := payload.get("exp")) and ((exp - int(time.time())) < 0):
            return errors.authentication_error(  # type: ignore
                None, errors.AuthenticationError("Token expired")
            )

        if payload.get("type") != "refresh":
            return errors.authentication_error(  # type: ignore
                None, errors.AuthenticationError("Token invalid")
            )
        else:
            user_id = int(payload["sub"])

    # TODO: Check if token is not revoked
    #       Add refresh token to the cache in order to check later
    # token_hash = security.hash_refresh_token(refresh_token)

    # Create new access token only
    access_token = security.create_access_token(user_id)

    return TokensPair(access_token=access_token, refresh_token=refresh_token)
