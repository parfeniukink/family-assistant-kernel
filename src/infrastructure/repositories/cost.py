from collections.abc import AsyncGenerator

from sqlalchemy import Result, Select, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.domain.transactions.cost import CostCategory
from src.infrastructure import database, errors


class Cost(database.DataAccessLayer):
    def __init__(self, session: AsyncSession | None = None) -> None:
        super().__init__(session)

    async def cost_categories(
        self,
    ) -> AsyncGenerator[CostCategory, None]:
        """get all items from 'cost_categories' table"""

        async with self._read_session() as session:
            results: Result = await session.execute(
                select(database.CostCategory)
            )
            for item in results.scalars():
                yield item

    async def add_cost_category(
        self, candidate: database.CostCategory
    ) -> database.CostCategory:
        """add item to the 'cost_categories' table."""

        self._write_session.add(candidate)
        return candidate

    async def costs(self, /, **kwargs) -> AsyncGenerator[database.Cost, None]:
        """get all items from 'costs' table.

        notes:
            kwargs are passed to
            the self._add_pagination_filters()
        """

        query: Select = (
            select(database.Cost)
            .options(
                joinedload(database.Cost.currency),
                joinedload(database.Cost.category),
                joinedload(database.Cost.user),
            )
            .order_by(database.Cost.timestamp)
        )

        query = self._add_pagination_filters(query, **kwargs)

        async with self._read_session() as session:
            results: Result = await session.execute(query)
            for item in results.scalars():
                yield item

    async def cost(self, id_: int) -> database.Cost:
        """get specific item from 'costs' table"""

        async with self._read_session() as session:
            results: Result = await session.execute(
                select(database.Cost)
                .where(database.Cost.id == id_)
                .options(
                    joinedload(database.Cost.currency),
                    joinedload(database.Cost.category),
                    joinedload(database.Cost.user),
                )
            )
            if not (item := results.scalars().one_or_none()):
                raise errors.NotFoundError(f"Cost {id_} not found")
        return item

    async def add_cost(self, candidate: database.Cost) -> database.Cost:
        """add item to the 'costs' table."""

        self._write_session.add(candidate)
        return candidate

    async def update_cost(
        self, candidate: database.Cost, **values
    ) -> database.Cost:

        query = (
            update(database.Cost)
            .where(database.Cost.id == candidate.id)
            .values(values)
            .returning(database.Cost)
        )

        await self._write_session.execute(query)

        return candidate

    # ==================================================
    # cost shortcuts section
    # ==================================================
    async def cost_shortcuts(
        self, user_id: int
    ) -> AsyncGenerator[database.CostShortcut, None]:
        """return all the cost shortcuts from the
        database.
        """

        query: Select = (
            select(database.CostShortcut)
            .where(database.CostShortcut.user_id == user_id)
            .options(
                joinedload(database.CostShortcut.currency),
                joinedload(database.CostShortcut.category),
            )
            .order_by(database.CostShortcut.id)
        )

        async with self._read_session() as session:
            results: Result = await session.execute(query)
            for item in results.scalars():
                yield item

    async def add_cost_shortcut(
        self, candidate: database.CostShortcut
    ) -> database.CostShortcut:
        """add item to the 'cost_shortcuts' table."""

        self._write_session.add(candidate)
        return candidate

    async def last_cost_shortcut(self, user_id: int) -> database.CostShortcut:
        query: Select = (
            select(database.CostShortcut)
            .where(database.CostShortcut.user_id == user_id)
            .order_by(desc(database.CostShortcut.ui_position_index))
            .limit(1)
        )

        async with self._read_session() as session:
            result: Result = await session.execute(query)
            if (shortcut := result.scalar_one_or_none()) is None:
                raise errors.NotFoundError("No shortcuts for user")
            else:
                return shortcut

    async def cost_shortcut(
        self, user_id: int, id_: int
    ) -> database.CostShortcut:
        """get specific item from 'cost_shortcuts'
        table.
        """

        async with self._read_session() as session:
            results: Result = await session.execute(
                select(database.CostShortcut)
                .where(
                    database.CostShortcut.id == id_,
                    database.CostShortcut.user_id == user_id,
                )
                .options(
                    joinedload(database.CostShortcut.currency),
                    joinedload(database.CostShortcut.category),
                )
            )
            if not (item := results.scalars().one_or_none()):
                raise errors.NotFoundError(f"Cost Shortcut {id_} not found")

        return item

    async def cost_shortcut_update_positions(
        self,
        user_id: int,
        values: list[dict[str, int]],
    ) -> None:
        """Update items in database.

        ARGS
        (1) user_id. For permissions
        (2) values.
            ex: [{
                    'id': 1,
                    'ui_position_index': 8,
                },
                {
                    'id': 2,
                    'ui_position_index': 7,
                }],
            Where 1 and 2 are cost shortcuts ids,
            and 8, 7 are postigion indexes


        VALIDATION ( `values` )
        (1) Position indexes could be only integers
            of 1..N
        (2) No duplicates and no 'missing' integers
            between 1 and N
        """

        ids = [v["id"] for v in values]
        positions = [v["ui_position_index"] for v in values]

        n = len(positions)
        if sorted(positions) != list(range(n)):
            raise ValueError(
                "Position indices must be the "
                "consecutive "
                f"sequence 1..{n}, got: {positions}"
            )
        if len(set(positions)) != n:
            raise ValueError("Position indices must be unique")
        if len(set(ids)) != n:
            raise ValueError("ID list contains duplicates")

        # Check user ownership
        q = select(database.CostShortcut.id).where(
            (database.CostShortcut.id.in_(ids))
            & (database.CostShortcut.user_id == user_id)
        )
        result = await self._write_session.execute(q)
        found_ids = {row[0] for row in result.all()}
        missing = set(ids) - found_ids
        if missing:
            raise ValueError(
                "Shortcuts not found or not " f"owned by user: {missing}"
            )

        # Update each record with a separate update
        # query.
        # PERF: Optimize with bulk update and
        # `Session.bulk_update_mappings()`
        for value in values:
            stmt = (
                update(database.CostShortcut)
                .where(
                    database.CostShortcut.id == value["id"],
                    database.CostShortcut.user_id == user_id,
                )
                .values(ui_position_index=value["ui_position_index"])
            )
            await self._write_session.execute(stmt)

    async def rebuild_ui_positions(self, user_id: int) -> None:
        # Get all shortcuts for user,
        # ordered by current position
        # (and id for stability)
        query = (
            select(database.CostShortcut)
            .where(database.CostShortcut.user_id == user_id)
            .order_by(
                database.CostShortcut.ui_position_index,
                database.CostShortcut.id,
            )
        )
        result = await self._write_session.execute(query)
        shortcuts = result.scalars().all()

        # Assign new consecutive positions
        for new_index, shortcut in enumerate(shortcuts, start=1):
            if shortcut.ui_position_index != new_index:
                stmt = (
                    update(database.CostShortcut)
                    .where(
                        database.CostShortcut.id == shortcut.id,
                        database.CostShortcut.user_id == user_id,
                    )
                    .values(ui_position_index=new_index)
                )
                await self._write_session.execute(stmt)
