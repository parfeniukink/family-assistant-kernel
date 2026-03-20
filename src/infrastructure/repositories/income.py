from collections.abc import AsyncGenerator

from sqlalchemy import Result, Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.infrastructure import database, errors


class Income(database.DataAccessLayer):
    def __init__(self, session: AsyncSession | None = None) -> None:
        super().__init__(session)

    async def incomes(
        self, /, **kwargs
    ) -> AsyncGenerator[database.Income, None]:
        """get all incomes from 'incomes' table

        notes:
            kwargs are passed to
            the self._add_pagination_filters()
        """

        query: Select = (
            select(database.Income)
            .options(
                joinedload(database.Income.currency),
                joinedload(database.Income.user),
            )
            .order_by(database.Income.timestamp)
        )

        query = self._add_pagination_filters(query, **kwargs)

        async with self._read_session() as session:
            results: Result = await session.execute(query)
            for item in results.scalars():
                yield item

    async def income(self, id_: int) -> database.Income:
        """get specific item from 'incomes' table"""

        async with self._read_session() as session:
            results: Result = await session.execute(
                select(database.Income)
                .where(database.Income.id == id_)
                .options(
                    joinedload(database.Income.currency),
                    joinedload(database.Income.user),
                )
            )
            if not (item := results.scalars().one_or_none()):
                raise errors.NotFoundError(f"Income {id_} not found")
        return item

    async def add_income(self, candidate: database.Income) -> database.Income:
        """add item to the 'incomes' table."""

        self._write_session.add(candidate)
        return candidate

    async def update_income(
        self, candidate: database.Income, **values
    ) -> database.Income:

        query = (
            update(database.Income)
            .where(database.Income.id == candidate.id)
            .values(values)
            .returning(database.Income)
        )

        await self._write_session.execute(query)

        return candidate
