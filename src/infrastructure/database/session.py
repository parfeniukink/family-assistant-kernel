import functools

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import settings


@functools.lru_cache(maxsize=1)
def engine_factory(**extra) -> AsyncEngine:
    engine = create_async_engine(
        settings.database.url,
        future=True,
        connect_args={"server_settings": {"timezone": settings.timezone}},
        **extra,
    )
    return engine


def session_factoy(
    engine: AsyncEngine | None = None,
) -> AsyncSession:
    """Creates a new async session to execute SQL queries."""

    return async_sessionmaker(
        engine or engine_factory(), expire_on_commit=False
    )()
