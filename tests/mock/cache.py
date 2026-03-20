from typing import Any, Self

from src.infrastructure import Cache as MemcachedCache
from src.infrastructure import errors


class Cache(MemcachedCache):
    """dict replacement for existing cache.

    ARGS
    ``_data`` - set for 'DEV purposes'. check this variable in test

    TODO
    instead of having the whole Cache class updated for the same purposes
    it is better to create a mocked full-Descriptor class to make it work
    with regular Python dictionary instead of speaking to separate service

    NOTES
    this class just mockes the inherited class
    """

    _data: dict[str, Any] = {}

    def __init__(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args, **kwargs) -> None:
        pass

    async def set(
        self,
        namespace: str,
        key: str,
        value: dict | list,
        exptime: int = 0,
    ) -> bool | None:
        Cache._data[f"{namespace}:{key}"] = value
        return True

    async def get(self, namespace: str, key: str) -> Any:
        if (result := Cache._data.get(f"{namespace}:{key}")) is None:
            raise errors.NotFoundError
        else:
            return result

    async def delete(self, namespace: str, key: str) -> bool:
        if Cache._data.get(f"{namespace}:{key}"):
            del Cache._data[f"{namespace}:{key}"]
            return True
        else:
            return False
