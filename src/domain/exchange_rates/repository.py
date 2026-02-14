from calendar import monthrange
from datetime import date

from sqlalchemy import Result, select

from src.infrastructure import database


class ExchangeRateRepository(database.Repository):
    """Repository for managing exchange rates."""

    async def get_rates(
        self, start_date: date, end_date: date
    ) -> list[database.ExchangeRate]:
        """Get all cached rates in the date range."""

        query = (
            select(database.ExchangeRate)
            .where(database.ExchangeRate.date.between(start_date, end_date))
            .order_by(database.ExchangeRate.date)
        )

        async with self.query.session as session:
            async with session.begin():
                result: Result = await session.execute(query)
                return list(result.scalars().all())

    async def get_existing_dates(
        self, cc_to: str, start_date: date, end_date: date
    ) -> set[date]:
        """Get dates that already have rates for a currency.

        ARGS
        (1) cc_to: currency code to
        (2) cc_from: currency code to
        """

        query = select(database.ExchangeRate.date).where(
            database.ExchangeRate.cc_from == "UAH",
            database.ExchangeRate.cc_to == cc_to,
            database.ExchangeRate.date.between(start_date, end_date),
        )

        async with self.query.session as session:
            async with session.begin():
                result: Result = await session.execute(query)
                return {row[0] for row in result.all()}

    async def get_monthly_rates(
        self, cc_to: str, year: int, month: int
    ) -> list[database.ExchangeRate]:
        """Get all rates for a currency within a specific month."""

        first = date(year, month, 1)
        last = date(year, month, monthrange(year, month)[1])

        query = (
            select(database.ExchangeRate)
            .where(
                database.ExchangeRate.cc_from == "UAH",
                database.ExchangeRate.cc_to == cc_to,
                database.ExchangeRate.date.between(first, last),
            )
            .order_by(database.ExchangeRate.date)
        )

        async with self.query.session as session:
            async with session.begin():
                result: Result = await session.execute(query)
                return list(result.scalars().all())

    async def add_rate(
        self, candidate: database.ExchangeRate
    ) -> database.ExchangeRate:
        """Insert a single rate (within transaction context)."""

        self.command.session.add(candidate)
        return candidate
