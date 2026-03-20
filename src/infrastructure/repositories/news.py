from datetime import date

from sqlalchemy import (
    Result,
    Select,
    String,
    cast,
    delete,
    desc,
    func,
    select,
    update,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Date

from src.infrastructure import database, errors
from src.infrastructure.cache import Cache


class News(database.DataAccessLayer):
    """Data access for news items and news sources."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        super().__init__(session)

    async def news_items(
        self, /, **kwargs
    ) -> tuple[tuple[database.NewsItem, ...], int]:
        """Paginated news items ordered by created_at DESC."""

        query: Select = select(database.NewsItem).order_by(
            desc(database.NewsItem.created_at)
        )
        count_query = select(func.count(database.NewsItem.id))

        query = self._add_pagination_filters(query, **kwargs)

        async with self._read_session() as session:
            count_result: Result = await session.execute(count_query)
            total = count_result.scalar() or 0

            result: Result = await session.execute(query)
            items = tuple(result.scalars().all())

        return items, total

    async def distinct_news_days(
        self, /, offset: int = 0, limit: int = 10
    ) -> list[date]:
        """Return distinct days that have news, newest first."""

        day_col = cast(database.NewsItem.created_at, Date).label("day")

        query = (
            select(day_col)
            .distinct()
            .order_by(day_col.desc())
            .offset(offset)
            .limit(limit)
        )

        async with self._read_session() as session:
            result: Result = await session.execute(query)
            return list(result.scalars().all())

    async def news_items_for_days(
        self, days: list[date]
    ) -> dict[date, list[database.NewsItem]]:
        """Return all news items for the given days, grouped."""

        if not days:
            return {}

        day_col = cast(database.NewsItem.created_at, Date)

        query = (
            select(database.NewsItem)
            .where(day_col.in_(days))
            .order_by(
                day_col.desc(),
                database.NewsItem.created_at.desc(),
            )
        )

        async with self._read_session() as session:
            result: Result = await session.execute(query)
            items = list(result.scalars().all())

        grouped: dict[date, list[database.NewsItem]] = {d: [] for d in days}
        for item in items:
            key = item.created_at.date()
            if key in grouped:
                grouped[key].append(item)

        return grouped

    async def news_items_for_date_range(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        *,
        bookmarked: bool | None = None,
        reaction: str | None = None,
        commented: bool | None = None,
    ) -> dict[date, list[database.NewsItem]]:
        """Return news items grouped by date.

        When start_date/end_date are provided, filters to that
        calendar range. Otherwise returns all matching items.
        """

        day_col = cast(database.NewsItem.created_at, Date)

        query = select(database.NewsItem).order_by(
            day_col.desc(),
            database.NewsItem.created_at.desc(),
        )

        if start_date is not None and end_date is not None:
            query = query.where(day_col.between(start_date, end_date))

        if bookmarked is not None:
            query = query.where(database.NewsItem.bookmarked.is_(bookmarked))
        if reaction is not None:
            query = query.where(database.NewsItem.reaction == reaction)
        if commented is True:
            query = query.where(database.NewsItem.human_feedback.isnot(None))
        elif commented is False:
            query = query.where(database.NewsItem.human_feedback.is_(None))

        async with self._read_session() as session:
            result: Result = await session.execute(query)
            items = list(result.scalars().all())

        grouped: dict[date, list[database.NewsItem]] = {}
        for item in items:
            key = item.created_at.date()
            grouped.setdefault(key, []).append(item)

        return grouped

    async def earliest_news_date(self) -> date | None:
        """Return the earliest date that has news items."""

        query = select(func.min(cast(database.NewsItem.created_at, Date)))

        async with self._read_session() as session:
            result: Result = await session.execute(query)
            return result.scalar()

    async def count_distinct_news_days(self) -> int:
        """Total number of distinct days with news."""

        day_col = cast(database.NewsItem.created_at, Date).label("day")

        query = select(func.count()).select_from(
            select(day_col).distinct().subquery()
        )

        async with self._read_session() as session:
            result: Result = await session.execute(query)
            return result.scalar() or 0

    async def existing_article_urls(self, limit: int = 200) -> set[str]:
        """Return all article URLs from recent news items.

        Unnests the article_urls arrays and returns a flat
        set for O(1) dedup lookups.
        """

        query = (
            select(func.unnest(database.NewsItem.article_urls))
            .order_by(desc(database.NewsItem.created_at))
            .limit(limit)
        )

        async with self._read_session() as session:
            result: Result = await session.execute(query)
            return set(result.scalars().all())

    async def set_human_feedback(
        self, id_: int, feedback: str | None
    ) -> database.NewsItem:
        """Set or clear human feedback on a news item."""

        query = (
            update(database.NewsItem)
            .where(database.NewsItem.id == id_)
            .values(
                human_feedback=feedback,
                needs_ai_analysis=True,
            )
            .returning(database.NewsItem)
        )
        result = await self._write_session.execute(query)
        row = result.scalar_one_or_none()
        if row is None:
            raise errors.NotFoundError(f"News item {id_} not found")
        return row

    async def recent_feedback(self, limit: int = 50) -> list[tuple[str, str]]:
        """Return (title, human_feedback) pairs for recent
        items that have feedback, newest first."""

        query = (
            select(
                database.NewsItem.title,
                database.NewsItem.human_feedback,
            )
            .where(database.NewsItem.human_feedback.isnot(None))
            .order_by(desc(database.NewsItem.created_at))
            .limit(limit)
        )

        async with self._read_session() as session:
            result: Result = await session.execute(query)
            return list(result.tuples().all())

    async def set_description_field(
        self, id_: int, column: str, text: str
    ) -> None:
        """Store AI-generated description in the given column."""

        query = (
            update(database.NewsItem)
            .where(database.NewsItem.id == id_)
            .values(**{column: text, "needs_ai_analysis": True})
        )
        await self._write_session.execute(query)

    async def get_news_item(self, id_: int) -> database.NewsItem:
        """Get a single news item by ID."""

        query = select(database.NewsItem).where(database.NewsItem.id == id_)

        async with self._read_session() as session:
            result: Result = await session.execute(query)
            item = result.scalar_one_or_none()

        if item is None:
            raise errors.NotFoundError(f"News item {id_} not found")
        return item

    async def delete_news_item(self, id_: int) -> None:
        """Delete a news item by ID."""

        query = (
            delete(database.NewsItem)
            .where(database.NewsItem.id == id_)
            .returning(database.NewsItem.id)
        )

        result = await self._write_session.execute(query)
        if result.scalar_one_or_none() is None:
            raise errors.NotFoundError(f"News item {id_} not found")

    async def toggle_bookmark(self, id_: int) -> database.NewsItem:
        """Toggle the bookmarked flag on a news item."""

        # Read current state
        q = select(database.NewsItem).where(database.NewsItem.id == id_)
        result = await self._write_session.execute(q)
        item = result.scalar_one_or_none()
        if item is None:
            raise errors.NotFoundError(f"News item {id_} not found")

        query = (
            update(database.NewsItem)
            .where(database.NewsItem.id == id_)
            .values(
                bookmarked=not item.bookmarked,
                needs_ai_analysis=True,
            )
            .returning(database.NewsItem)
        )

        result = await self._write_session.execute(query)
        return result.scalar_one()

    async def set_reaction(
        self, id_: int, reaction: str | None
    ) -> database.NewsItem:
        """Set or clear the reaction on a news item."""

        query = (
            update(database.NewsItem)
            .where(database.NewsItem.id == id_)
            .values(
                reaction=reaction,
                needs_ai_analysis=True,
            )
            .returning(database.NewsItem)
        )

        result = await self._write_session.execute(query)
        row = result.scalar_one_or_none()
        if row is None:
            raise errors.NotFoundError(f"News item {id_} not found")
        return row

    async def add_news_item(
        self, candidate: database.NewsItem
    ) -> database.NewsItem:
        """Insert a new news item."""

        self._write_session.add(candidate)
        return candidate

    async def merge_articles(
        self, id_: int, description: str, urls: list[str]
    ) -> None:
        """Merge content and URLs into an existing item."""

        query = (
            update(database.NewsItem)
            .where(database.NewsItem.id == id_)
            .values(
                description=description,
                article_urls=func.array_cat(
                    database.NewsItem.article_urls,
                    cast(urls, postgresql.ARRAY(String)),
                ),
            )
        )
        await self._write_session.execute(query)

    async def today_news_items(self) -> list[database.NewsItem]:
        """Return all news items created today."""

        day_col = cast(database.NewsItem.created_at, Date)

        query = (
            select(database.NewsItem)
            .where(day_col == date.today())
            .order_by(database.NewsItem.created_at.desc())
        )

        async with self._read_session() as session:
            result: Result = await session.execute(query)
            return list(result.scalars().all())

    async def stale_item_titles(
        self, before_date: date, limit: int = 20
    ) -> list[str]:
        """Return titles of unreacted items that would be GC'd."""

        day_col = cast(database.NewsItem.created_at, Date)
        query = (
            select(database.NewsItem.title)
            .where(day_col < before_date)
            .where(database.NewsItem.reaction.is_(None))
            .where(database.NewsItem.bookmarked.is_(False))
            .where(database.NewsItem.human_feedback.is_(None))
            .order_by(database.NewsItem.created_at.desc())
            .limit(limit)
        )

        async with self._read_session() as session:
            result: Result = await session.execute(query)
            return list(result.scalars().all())

    async def delete_stale_items(self, before_date: date) -> int:
        """Delete unreacted news items created before the given date.

        Returns the number of deleted items.
        """

        day_col = cast(database.NewsItem.created_at, Date)
        query = (
            delete(database.NewsItem)
            .where(day_col < before_date)
            .where(database.NewsItem.reaction.is_(None))
            .where(database.NewsItem.bookmarked.is_(False))
            .where(database.NewsItem.human_feedback.is_(None))
            .returning(database.NewsItem.id)
        )
        result = await self._write_session.execute(query)
        return len(result.all())

    async def recent_reactions(self, since: date) -> list[database.NewsItem]:
        """Return items that need AI analysis since a given date."""

        day_col = func.date(database.NewsItem.created_at)
        query = (
            select(database.NewsItem)
            .where(database.NewsItem.needs_ai_analysis.is_(True))
            .where(day_col >= since)
            .order_by(desc(database.NewsItem.created_at))
        )

        async with self._read_session() as session:
            result: Result = await session.execute(query)
            return list(result.scalars().all())

    async def clear_ai_analysis_flag(self, ids: list[int]) -> None:
        """Mark news items as analyzed by the preference agent."""

        if not ids:
            return

        query = (
            update(database.NewsItem)
            .where(database.NewsItem.id.in_(ids))
            .values(needs_ai_analysis=False)
        )
        await self._write_session.execute(query)

    async def cache_seen_urls(self, urls: list[str]) -> None:
        """Cache URLs that have been analyzed (saved or filtered).
        TTL = 3 days. Stored as a single list under 'seen_urls:global'.
        """

        async with Cache() as cache:
            try:
                existing: list[str] = await cache.get("seen_urls", "global")
            except Exception:
                existing = []
            merged = list(dict.fromkeys(existing + urls))[-1000:]
            await cache.set("seen_urls", "global", merged, exptime=259200)

    async def cached_seen_urls(self) -> set[str]:
        """Return the set of cached seen URLs."""

        async with Cache() as cache:
            try:
                urls: list[str] = await cache.get("seen_urls", "global")
                return set(urls)
            except Exception:
                return set()

    async def url_exists(self, url: str) -> bool:
        """Check if a URL already exists in any article."""

        query = select(func.count()).where(
            database.NewsItem.article_urls.contains([url])
        )

        async with self._read_session() as session:
            result: Result = await session.execute(query)
            return (result.scalar() or 0) > 0
