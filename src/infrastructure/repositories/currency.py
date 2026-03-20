from sqlalchemy import Result, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure import database


class Currency(database.DataAccessLayer):
    def __init__(self, session: AsyncSession | None = None) -> None:
        super().__init__(session)

    async def currency(self, id_: int) -> database.Currency:
        """search by ``id``."""

        async with self._read_session() as session:
            results: Result = await session.execute(
                select(database.Currency).where(database.Currency.id == id_)
            )
            item: database.Currency = results.scalars().one()

        return item

    async def currencies(
        self,
    ) -> tuple[database.Currency, ...]:
        """select everything from 'currencies' table."""

        async with self._read_session() as session:
            result: Result = await session.execute(
                select(database.Currency).order_by(desc(database.Currency.id))
            )

        return tuple(result.scalars().all())

    async def add_currency(
        self, candidate: database.Currency
    ) -> database.Currency:
        """add item to the 'currencies' table."""

        self._write_session.add(candidate)
        return candidate

    async def decrease_equity(self, currency_id: int, value: int) -> None:
        """decrease the equity for a currency."""

        query = (
            update(database.Currency)
            .where(database.Currency.id == currency_id)
            .values({"equity": database.Currency.equity - value})
            .returning(database.Currency)
        )

        await self._write_session.execute(query)

    async def increase_equity(self, currency_id: int, value: int) -> None:
        """increase the equity for a currency."""

        query = (
            update(database.Currency)
            .where(database.Currency.id == currency_id)
            .values({"equity": database.Currency.equity + value})
            .returning(database.Currency)
        )

        await self._write_session.execute(query)
