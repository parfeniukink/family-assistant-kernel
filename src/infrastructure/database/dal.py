from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from loguru import logger
from sqlalchemy import Result, Select, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure import errors

from .session import session_factoy


class DataAccessLayer:
    """Base data access layer with session management.

    Read methods: create a fresh session per call via _read_session().
    Write methods: use a shared write session via _write_session,
    committed via flush().
    """

    def __init__(self, session: AsyncSession | None = None) -> None:
        self._external_session = session is not None
        self._session = session

    @asynccontextmanager
    async def _read_session(
        self,
    ) -> AsyncGenerator[AsyncSession, None]:
        """New session for each read."""

        session = session_factoy()
        try:
            yield session
        except errors.NotFoundError:
            raise
        except Exception as error:
            logger.error(error)
            raise errors.DatabaseError(str(error)) from error
        finally:
            await session.close()

    @property
    def _write_session(self) -> AsyncSession:
        """Shared session for writes."""

        if self._session is None:
            self._session = session_factoy()
        return self._session

    async def flush(self) -> None:
        """Commit pending writes to database."""

        if self._session is None:
            return
        if self._external_session:
            return  # caller manages commit

        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
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
        finally:
            await self._session.close()
            self._session = None

    async def count(self, table, **filters) -> int:
        """get the number of items in a table"""

        _filters: dict = {
            key: value for key, value in filters.items() if value
        }

        try:
            query: Select = select(func.count(getattr(table, "id")))
            for attr, value in _filters.items():
                query = getattr(query, "where")(getattr(table, attr) == value)
        except AttributeError as error:
            raise errors.DatabaseError(
                f"``id`` does not exist for {table} "
            ) from error

        async with self._read_session() as session:
            result: Result = await session.execute(query)
            value = result.scalar()

            if not isinstance(value, int):
                raise errors.DatabaseError(
                    message=(
                        "Database count() function returned "
                        "no-integer "
                        f"({type(value)}) type of value"
                    ),
                )
            else:
                return value

    def _add_pagination_filters(
        self, query, /, offset: int = 0, limit: int = 10, **_
    ):
        """update the query if pagination filters are specified.

        params:
            ``offset: int | None`` to apply filter `OFFSET {last_id}`
            ``limit: int | None`` to apply filter `LIMIT {limit}`
        """

        if offset < 0:
            raise ValueError("Wrong ``offset`` on pagination")
        elif offset > 0:
            query = query.offset(offset)

        if limit < 0:
            raise ValueError("Wrong ``limit`` on pagination")
        elif limit > 0:
            query = query.limit(limit)

        return query

    async def delete(self, table, candidate_id: int) -> None:
        """Delete a record from the specified table."""

        query = delete(table).where(getattr(table, "id") == candidate_id)
        await self._write_session.execute(query)
