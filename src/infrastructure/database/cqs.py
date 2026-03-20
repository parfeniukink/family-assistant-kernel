"""
CQS (Command Query Separation) transaction support.

Provides a shared-session transaction() context manager for
cross-repository writes. Individual repositories manage their
own sessions via the Repository base class.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure import errors

from .session import session_factoy


@asynccontextmanager
async def transaction() -> AsyncGenerator[AsyncSession, None]:
    """Shared session for cross-repository writes.

    Usage:
        async with transaction() as session:
            repo_a = SomeRepository(session=session)
            repo_b = OtherRepository(session=session)
            await repo_a.do_write(...)
            await repo_b.do_write(...)
            # auto-commits on context exit
    """

    session: AsyncSession = session_factoy()

    try:
        async with session.begin():
            yield session
    except IntegrityError as error:
        _error = str(error)

        if "duplicate key value violates unique constraint" in _error:
            logger.debug(f"Database Duplication Error: {_error}")
            raise errors.UnprocessableRequestError(
                "Some of the fields must be unique in database"
            ) from error
        elif "ForeignKeyViolationError" in _error:
            logger.debug(f"Database Foreign Key Violation Error: {_error}")
            raise errors.BadRequestError("Invalid input") from error
        else:
            logger.error(f"Unhandled database error: {_error}")
            raise

    except errors.NotFoundError as error:
        logger.error(error)
        raise error
    except Exception as error:
        logger.error(error)
        raise errors.DatabaseError(str(error)) from error
    finally:
        await session.close()
