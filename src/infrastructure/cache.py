import asyncio
import contextlib
import json
import pickle
from typing import Any, Self

from aiomcache import FlagClient

from src.config import settings
from src.infrastructure import errors


class Cache:
    """client for ``memcached``.

    USAGE
    >>> async with Cache() as cache:
    >>>     await cache.set('namespace', 'key', {"key": "value"})
    >>>     await cache.get('namespace', 'key')

    SIDE EFFECTS
        - client close the connection on ``Cache.__aexit__``
    """

    @staticmethod
    async def set_flag_handler(value):
        return pickle.dumps(value), 1

    @staticmethod
    async def get_flag_handler(value: bytes, flags: int):
        if flags == 1:
            return value
        raise ValueError(f"unrecognized flag: {flags}")

    def __init__(self) -> None:
        self._client: FlagClient | None = None

    async def __aenter__(self) -> Self:
        self._client = FlagClient(
            settings.cache.host,
            settings.cache.port,
            set_flag_handler=self.set_flag_handler,
            get_flag_handler=self.get_flag_handler,
        )
        return self

    async def __aexit__(self, *args, **kwargs) -> None:
        with contextlib.suppress(RuntimeError):
            loop = asyncio.get_running_loop()
            loop.create_task(self.client.close())

    @property
    def client(self) -> FlagClient:
        if self._client is None:
            raise Exception(f"Bad usage. {self.__class__.__doc__}")
        else:
            return self._client

    async def set(
        self,
        namespace: str,
        key: str,
        value: dict | list,
        exptime: int = 0,
    ) -> bool | None:

        instance = await self.client.set(
            f"{namespace}:{key}".encode(),
            json.dumps(value).encode(),
            exptime=exptime,
        )

        return instance

    async def get(self, namespace: str, key: str) -> Any:
        result: bytes | None = await self.client.get(
            f"{namespace}:{key}".encode()
        )

        if result is None:
            raise errors.NotFoundError

        try:
            return json.loads(result)
        except json.JSONDecodeError as error:
            raise ValueError(
                "cache value must be JSON serializable"
            ) from error

    async def delete(self, namespace: str, key: str) -> bool:
        return await self.client.delete(f"{namespace}:{key}".encode())
