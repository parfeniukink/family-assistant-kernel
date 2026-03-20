from collections.abc import AsyncGenerator

from sqlalchemy import Result, select, update
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.domain.equity import Currency
from src.domain.transactions import CostCategory
from src.domain.users import User as DomainUser
from src.domain.users import UserConfiguration
from src.infrastructure import database, errors


def _to_domain(instance: database.User) -> DomainUser:
    """Convert a database User ORM object to a domain User."""

    return DomainUser(
        id=instance.id,
        name=instance.name,
        configuration=UserConfiguration(
            show_equity=instance.show_equity,
            cost_snippets=instance.cost_snippets,
            income_snippets=instance.income_snippets,
            default_currency=(
                Currency.model_validate(instance.default_currency)
                if instance.default_currency
                else None
            ),
            default_cost_category=(
                CostCategory.model_validate(instance.default_cost_category)
                if instance.default_cost_category
                else None
            ),
            last_notification=instance.last_notification,
            notify_cost_threshold=instance.notify_cost_threshold,
            monobank_api_key=instance.monobank_api_key,
            news_filter_prompt=instance.news_filter_prompt,
            news_preference_profile=(instance.news_preference_profile),
            gc_retention_days=instance.gc_retention_days,
            analyze_preferences=instance.analyze_preferences,
            timezone=instance.timezone,
        ),
    )


class User(database.DataAccessLayer):
    def __init__(self, session: AsyncSession | None = None) -> None:
        super().__init__(session)

    async def user_by_id(self, id_: int) -> DomainUser:
        """Search by ``id``. Returns domain User."""

        async with self._read_session() as session:
            results: Result = await session.execute(
                select(database.User)
                .where(database.User.id == id_)
                .options(
                    joinedload(database.User.default_currency),
                    joinedload(database.User.default_cost_category),
                )
            )
            user: database.User = results.scalars().one()

        return _to_domain(user)

    async def excluding(self, id_: int) -> DomainUser:
        """Exclude concrete user from results."""

        async with self._read_session() as session:
            results: Result = await session.execute(
                select(database.User)
                .where(database.User.id != id_)
                .options(
                    joinedload(database.User.default_currency),
                    joinedload(database.User.default_cost_category),
                )
            )
            user: database.User = results.scalars().one()

        return _to_domain(user)

    async def user_for_auth(self, name: str) -> database.User:
        """Search by name for authentication.

        Returns raw database User (needed for password_hash).
        """

        async with self._read_session() as session:
            results: Result = await session.execute(
                select(database.User).where(database.User.name == name)
            )
            try:
                user: database.User = results.scalars().one()
            except NoResultFound as error:
                raise errors.NotFoundError("Can't find user") from error

        return user

    async def by_cost_threshold_notification(
        self, cost: database.Cost
    ) -> AsyncGenerator[DomainUser, None]:
        """Exclude current user. Select users by threshold."""

        async with self._read_session() as session:
            results: Result = await session.execute(
                select(database.User)
                .where(
                    database.User.id != cost.user_id,
                    cost.value >= database.User.notify_cost_threshold,
                )
                .options(
                    joinedload(database.User.default_currency),
                    joinedload(database.User.default_cost_category),
                )
            )

            for item in results.scalars():
                yield _to_domain(item)

    async def all_users(self) -> list[DomainUser]:
        """Return all users."""

        async with self._read_session() as session:
            results = await session.execute(
                select(database.User).options(
                    joinedload(database.User.default_currency),
                    joinedload(database.User.default_cost_category),
                )
            )
            return [_to_domain(u) for u in results.scalars()]

    async def add_user(self, candidate: database.User) -> database.User:
        self._write_session.add(candidate)
        return candidate

    async def update_user(self, id_: int, **values) -> None:
        """Update user configuration fields."""

        query = (
            update(database.User).where(database.User.id == id_).values(values)
        )

        await self._write_session.execute(query)
