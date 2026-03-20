from collections.abc import AsyncGenerator

from sqlalchemy import Result, Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.infrastructure import database, errors


class Exchange(database.DataAccessLayer):
    def __init__(self, session: AsyncSession | None = None) -> None:
        super().__init__(session)

    async def exchanges(
        self, /, **kwargs
    ) -> AsyncGenerator[database.Exchange, None]:
        """get all exchanges from 'exchanges' table"""

        query: Select = (
            select(database.Exchange)
            .options(
                joinedload(database.Exchange.from_currency),
                joinedload(database.Exchange.to_currency),
                joinedload(database.Exchange.user),
            )
            .order_by(database.Exchange.timestamp)
        )

        query = self._add_pagination_filters(query, **kwargs)

        async with self._read_session() as session:
            results: Result = await session.execute(query)
            for item in results.scalars():
                yield item

    async def exchange(self, id_: int) -> database.Exchange:
        """get specific item from 'exchange' table"""

        async with self._read_session() as session:
            results: Result = await session.execute(
                select(database.Exchange)
                .where(database.Exchange.id == id_)
                .options(
                    joinedload(database.Exchange.from_currency),
                    joinedload(database.Exchange.to_currency),
                    joinedload(database.Exchange.user),
                )
            )
            if not (item := results.scalars().one_or_none()):
                raise errors.NotFoundError(f"Exchange {id_} not found")

        return item

    async def add_exchange(
        self, candidate: database.Exchange
    ) -> database.Exchange:
        """add item to the 'exchanges' table."""

        self._write_session.add(candidate)
        return candidate
