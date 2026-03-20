import asyncpg
from aiomcache import Client
from loguru import logger

from src.config import settings


async def database_connection() -> None:
    try:
        connection: asyncpg.Connection = await asyncpg.connect(
            host=settings.database.host,
            port=settings.database.port,
            user=settings.database.user,
            password=settings.database.password,
            database=settings.database.name,
        )
    except asyncpg.exceptions.PostgresError as error:
        raise SystemExit(
            "can not connect to the dataabse. "
            "check if ``postgresql`` is running"
        ) from error
    else:
        version: str = await connection.fetchval("SELECT version();")
        logger.success(f"{version} is connected")
        await connection.close()


async def cache_connection() -> None:
    client = Client(settings.cache.host, settings.cache.port)

    try:
        version: bytes = await client.version()
    except ConnectionRefusedError as error:
        raise SystemExit(
            "cannot connect to the cache. check if ``memcached`` is running"
        ) from error
    else:
        logger.success(f"Memcached v{version.decode()} is connected")
        await client.close()
