from calendar import monthrange
from datetime import date

from sqlalchemy import Result, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure import database


class ExchangeRate(database.DataAccessLayer):
    """Repository for managing exchange rates."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        super().__init__(session)

    async def get_rates(
        self, start_date: date, end_date: date
    ) -> list[database.ExchangeRate]:
        """Get all cached rates in the date range."""

        query = (
            select(database.ExchangeRate)
            .where(database.ExchangeRate.date.between(start_date, end_date))
            .order_by(database.ExchangeRate.date)
        )

        async with self._read_session() as session:
            result: Result = await session.execute(query)
            return list(result.scalars().all())

    async def get_existing_dates(
        self,
        cc_to: str,
        start_date: date,
        end_date: date,
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

        async with self._read_session() as session:
            result: Result = await session.execute(query)
            return {row[0] for row in result.all()}

    async def get_monthly_rates(
        self, cc_to: str, year: int, month: int
    ) -> list[database.ExchangeRate]:
        """Get all rates for a currency within a month."""

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

        async with self._read_session() as session:
            result: Result = await session.execute(query)
            return list(result.scalars().all())

    async def get_closest_rate(
        self, cc_to: str, target_date: date
    ) -> database.ExchangeRate | None:
        """Find the single closest rate by date for a currency.

        Strategy: two queries (closest before + closest after),
        pick the nearest. Returns None only if no rates exist
        at all for that currency.
        """

        before_query = (
            select(database.ExchangeRate)
            .where(
                database.ExchangeRate.cc_from == "UAH",
                database.ExchangeRate.cc_to == cc_to,
                database.ExchangeRate.date <= target_date,
            )
            .order_by(database.ExchangeRate.date.desc())
            .limit(1)
        )

        after_query = (
            select(database.ExchangeRate)
            .where(
                database.ExchangeRate.cc_from == "UAH",
                database.ExchangeRate.cc_to == cc_to,
                database.ExchangeRate.date >= target_date,
            )
            .order_by(database.ExchangeRate.date.asc())
            .limit(1)
        )

        async with self._read_session() as session:
            before_result = await session.execute(before_query)
            before_rate = before_result.scalar_one_or_none()

            after_result = await session.execute(after_query)
            after_rate = after_result.scalar_one_or_none()

        if before_rate is None and after_rate is None:
            return None
        if before_rate is None:
            return after_rate
        if after_rate is None:
            return before_rate

        before_diff = abs((target_date - before_rate.date).days)
        after_diff = abs((after_rate.date - target_date).days)

        return before_rate if before_diff <= after_diff else after_rate

    async def add_rate(
        self, candidate: database.ExchangeRate
    ) -> database.ExchangeRate:
        """Insert a single rate (within transaction context)."""

        self._write_session.add(candidate)
        return candidate
