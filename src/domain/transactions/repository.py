import asyncio
import itertools
import operator
from collections.abc import AsyncGenerator
from datetime import date

from sqlalchemy import (
    Result,
    Select,
    String,
    delete,
    desc,
    func,
    select,
    union_all,
    update,
)
from sqlalchemy.orm import aliased, joinedload

from src.domain.equity import Currency
from src.domain.users import User
from src.infrastructure import database, dates, errors

from .entities import CostCategory
from .value_objects import (
    CostsByCategory,
    IncomesBySource,
    Transaction,
    TransactionsBasicAnalytics,
    TransactionsFilter,
)


class TransactionRepository(database.Repository):
    """
    ``TransactionRepository`` is a data access entrypoint.
    it allows manage costs, incomes, exchanges.

    it uses the 'Query Builder' to create SQL queries.
    """

    # ==================================================
    # unified || aggregated section
    # ==================================================
    async def transactions(  # noqa: C901 (too complex function)
        self,
        /,
        user: User,
        filter: TransactionsFilter = TransactionsFilter(),
        **pagination_kwargs,
    ) -> tuple[tuple[Transaction, ...], int]:
        """get all the items from 'costs', 'incomes', 'exchanges' tables
        in the internal representation.
        """

        CostCategoryAlias = aliased(database.CostCategory)
        CurrencyAlias = aliased(database.Currency)
        UserAlias = aliased(database.User)

        # select costs
        cost_query = (
            select(
                database.Cost.id.label("id"),
                database.Cost.name.label("name"),
                CostCategoryAlias.name.label("icon"),
                database.Cost.value.label("value"),
                database.Cost.timestamp.label("timestamp"),
                func.cast("cost", String).label(  # type: ignore[arg-type]
                    "operation_type",
                ),
                CurrencyAlias,
                UserAlias.name,
            )
            .join(CurrencyAlias, database.Cost.currency)
            .join(CostCategoryAlias, database.Cost.category)
            .join(UserAlias, database.Cost.user)
        )

        # select incomes
        income_query = (
            select(
                database.Income.id.label("id"),
                database.Income.name.label("name"),
                func.cast("🤑", String).label(  # type: ignore[arg-type]
                    "icon",
                ),
                database.Income.value.label("value"),
                database.Income.timestamp.label("timestamp"),
                func.cast("income", String).label(  # type: ignore[arg-type]
                    "operation_type",
                ),
                CurrencyAlias,
                UserAlias.name,
            )
            .join(CurrencyAlias, database.Income.currency)
            .join(UserAlias, database.Income.user)
        )

        # select exchanges
        exchange_query = (
            select(
                database.Exchange.id.label("id"),
                func.cast("exchange", String).label(  # type: ignore[arg-type]
                    "name",
                ),
                func.cast("💱", String).label(  # type: ignore[arg-type]
                    "icon",
                ),
                database.Exchange.to_value.label("value"),
                database.Exchange.timestamp.label("timestamp"),
                func.cast("exchange", String).label(  # type: ignore[arg-type]
                    "operation_type",
                ),
                CurrencyAlias,
                UserAlias.name,
            )
            .join(CurrencyAlias, database.Exchange.to_currency)
            .join(UserAlias, database.Exchange.user)
        )

        # add currency filter if specified
        if filter.only_mine is True:
            cost_query = cost_query.where(database.Cost.user_id == user.id)
            income_query = income_query.where(
                database.Income.user_id == user.id
            )
            exchange_query = exchange_query.where(
                database.Exchange.user_id == user.id
            )

        # add currency filter if specified
        if filter.currency_id is not None:
            cost_query = cost_query.where(
                database.Cost.currency_id == filter.currency_id
            )
            income_query = income_query.where(
                database.Income.currency_id == filter.currency_id
            )
            exchange_query = exchange_query.where(
                database.Exchange.to_currency_id == filter.currency_id
            )

        # add timesatmp filter if specified
        if filter.period or (filter.start_date and filter.end_date):
            if filter.period == "current-month":
                _start_date = dates.get_first_date_of_current_month()
                _end_date = date.today()
            elif filter.period == "previous-month":
                _start_date, _end_date = dates.get_previous_month_range()
            elif filter.start_date and filter.end_date:
                _start_date = filter.start_date
                _end_date = filter.end_date
            else:
                raise ValueError("Invalid dates range filter")

            cost_query = cost_query.where(
                database.Cost.timestamp.between(_start_date, _end_date)
            )
            income_query = income_query.where(
                database.Income.timestamp.between(_start_date, _end_date)
            )
            exchange_query = exchange_query.where(
                database.Exchange.timestamp.between(_start_date, _end_date)
            )

        if filter.cost_category_id is not None:
            cost_query = cost_query.where(
                database.Cost.category_id == filter.cost_category_id
            )

        if filter.pattern is not None:
            if filter.operation == "cost":
                cost_query = cost_query.where(
                    database.Cost.name.ilike(filter.pattern)
                )

            elif filter.operation == "cost":
                income_query = income_query.where(
                    database.Income.name.ilike(filter.pattern)
                )

        # combine all the queries using UNION ALL
        # apply operation filter if needed
        if filter.operation is None:
            queries: tuple[Select, ...] = (
                cost_query,
                income_query,
                exchange_query,
            )
        else:
            if filter.operation == "cost":
                queries = (cost_query,)
            elif filter.operation == "income":
                queries = (income_query,)
            elif filter.operation == "exchange":
                queries = (exchange_query,)

        final_query = (
            union_all(*queries)
            .order_by(desc("timestamp"))
            .order_by(desc("id"))
        )

        paginated_query = self._add_pagination_filters(
            final_query, **pagination_kwargs
        )
        count_query = select(func.count()).select_from(
            final_query,  # type: ignore[arg-type]
        )

        results: list[Transaction] = []

        # execute the query and map results to ``Transaction`` attributes
        async with self.query.session as session:
            async with session.begin():
                # calculate total
                count_result = await session.execute(count_query)
                if (total := count_result.scalar()) is None:
                    raise errors.DatabaseError("Can't get the total of items")

                result = await session.execute(paginated_query)
                for row in result:
                    (
                        id_,
                        name,
                        icon,
                        value,
                        timestamp,
                        operation_type,
                        currency_name,
                        currency_sign,
                        _,  # currency equity
                        _currency_id,
                        user_name,
                    ) = row

                    results.append(
                        Transaction(
                            id=id_,
                            name=name,
                            icon=icon,
                            value=value,
                            timestamp=timestamp,
                            operation=operation_type,
                            currency=Currency(
                                id=_currency_id,
                                name=currency_name,
                                sign=currency_sign,
                            ),
                            user=user_name,
                        )
                    )

        return tuple(results), total

    async def delete(self, table, candidate_id: int) -> None:
        """delete some specific trasaction from the specified table."""

        query = delete(table).where(getattr(table, "id") == candidate_id)
        await self.command.session.execute(query)

    # ==================================================
    # costs section
    # ==================================================
    async def cost_categories(self) -> AsyncGenerator[CostCategory, None]:
        """get all items from 'cost_categories' table"""

        async with self.query.session as session:
            async with session.begin():
                results: Result = await session.execute(
                    select(database.CostCategory)
                )
                for item in results.scalars():
                    yield item

    async def add_cost_category(
        self, candidate: database.CostCategory
    ) -> database.CostCategory:
        """add item to the 'cost_categories' table."""

        self.command.session.add(candidate)
        return candidate

    async def costs(self, /, **kwargs) -> AsyncGenerator[database.Cost, None]:
        """get all items from 'costs' table.

        notes:
            kwargs are passed to the self._add_pagination_filters()
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

        async with self.query.session as session:
            async with session.begin():
                results: Result = await session.execute(query)
                for item in results.scalars():
                    yield item

    async def cost(self, id_: int) -> database.Cost:
        """get specific item from 'costs' table"""

        async with self.query.session as session:
            async with session.begin():
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

        self.command.session.add(candidate)
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

        await self.command.session.execute(query)

        return candidate

    # ==================================================
    # incomes section
    # ==================================================
    async def incomes(
        self, /, **kwargs
    ) -> AsyncGenerator[database.Income, None]:
        """get all incomes from 'incomes' table

        notes:
            kwargs are passed to the self._add_pagination_filters()
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

        async with self.query.session as session:
            async with session.begin():
                results: Result = await session.execute(query)
                for item in results.scalars():
                    yield item

    async def income(self, id_: int) -> database.Income:
        """get specific item from 'incomes' table"""

        async with self.query.session as session:
            async with session.begin():
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

        self.command.session.add(candidate)
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

        await self.command.session.execute(query)

        return candidate

    # ==================================================
    # exchanges section
    # ==================================================
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

        async with self.query.session as session:
            async with session.begin():
                results: Result = await session.execute(query)
                for item in results.scalars():
                    yield item

    async def exchange(self, id_: int) -> database.Exchange:
        """get specific item from 'exchange' table"""

        async with self.query.session as session:
            async with session.begin():
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

        self.command.session.add(candidate)
        return candidate

    # ==================================================
    # cost shortcuts section
    # ==================================================
    async def cost_shortcuts(
        self, user_id: int
    ) -> AsyncGenerator[database.CostShortcut, None]:
        """return all the cost shortcuts from the  database."""

        query: Select = (
            select(database.CostShortcut)
            .where(database.CostShortcut.user_id == user_id)
            .options(
                joinedload(database.CostShortcut.currency),
                joinedload(database.CostShortcut.category),
            )
            .order_by(database.CostShortcut.id)
        )

        async with self.query.session as session:
            async with session.begin():
                results: Result = await session.execute(query)
                for item in results.scalars():
                    yield item

    async def add_cost_shortcut(
        self, candidate: database.CostShortcut
    ) -> database.CostShortcut:
        """add item to the 'cost_shortcuts' table."""

        self.command.session.add(candidate)
        return candidate

    async def last_cost_shortcut(self, user_id: int) -> database.CostShortcut:
        query: Select = (
            select(database.CostShortcut)
            .where(database.CostShortcut.user_id == user_id)
            .order_by(desc(database.CostShortcut.ui_position_index))
            .limit(1)
        )

        async with self.query.session as session:
            async with session.begin():
                result: Result = await session.execute(query)
                if (shortcut := result.scalar_one_or_none()) is None:
                    raise errors.NotFoundError("No shortcuts for user")
                else:
                    return shortcut

    async def cost_shortcut(
        self, user_id: int, id_: int
    ) -> database.CostShortcut:
        """get specific item from 'cost_shortcuts' table."""

        async with self.query.session as session:
            async with session.begin():
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
                    raise errors.NotFoundError(
                        f"Cost Shortcut {id_} not found"
                    )

        return item

    async def cost_shortcut_update_positions(
        self, user_id: int, values: list[dict[str, int]]
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
            Where 1 and 2 are cost shortcuts ids, and 8, 7 are
            postigion indexes


        VALIDATION ( `values` )
        (1) Position indexes could be only integers of 1..N
        (2) No duplicates and no 'missing' integers between 1 and N
        """

        ids = [v["id"] for v in values]
        positions = [v["ui_position_index"] for v in values]

        n = len(positions)
        if sorted(positions) != list(range(n)):
            raise ValueError(
                "Position indices must be the consecutive "
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
        result = await self.command.session.execute(q)
        found_ids = {row[0] for row in result.all()}
        missing = set(ids) - found_ids
        if missing:
            raise ValueError(
                f"Shortcuts not found or not owned by user: {missing}"
            )

        # Update each record with a separate update query.
        # PERF: Optimize with bulk update and `Session.bulk_update_mappings()`
        for value in values:
            stmt = (
                update(database.CostShortcut)
                .where(
                    database.CostShortcut.id == value["id"],
                    database.CostShortcut.user_id == user_id,
                )
                .values(ui_position_index=value["ui_position_index"])
            )
            await self.command.session.execute(stmt)

    async def rebuild_ui_positions(self, user_id: int) -> None:
        # Get all shortcuts for user,
        # ordered by current position (and id for stability)
        query = (
            select(database.CostShortcut)
            .where(database.CostShortcut.user_id == user_id)
            .order_by(
                database.CostShortcut.ui_position_index,
                database.CostShortcut.id,
            )
        )
        result = await self.command.session.execute(query)
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
                await self.command.session.execute(stmt)

    # ==================================================
    # analytics section
    # ==================================================
    async def transactions_basic_analytics(  # noqa: C901
        self,
        /,
        pattern: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> tuple[TransactionsBasicAnalytics, ...]:
        """build the transactions 'basic analytics' on the database level.

        args:
            ``currency_id`` - ID of the currency to filter by, if specified.
            ``start_date`` - Starting date of the analytics period.
            ``end_date`` - Ending date of the analytics period.


        workflow:
            build database queries. all (except of exchanges)
                are grouped by currency
            execute SQL queries asynchronously
            build the internal data structure to be returned

        notes:
            the 'key' of the result dictionary belongs
            to the `currency_id` of the related analytics block.
        """

        # validation
        if not any((pattern, all((start_date, end_date)))):
            raise errors.DatabaseError(
                "Whether pattern or dates range "
                "must be specified to get analytics"
            )

        # define filters
        cost_filters = []
        income_filters = []
        exchange_filters = []
        if start_date and end_date:
            cost_filters.append(
                database.Cost.timestamp.between(start_date, end_date)
            )
            income_filters.append(
                database.Income.timestamp.between(start_date, end_date)
            )
            exchange_filters.append(
                database.Exchange.timestamp.between(start_date, end_date)
            )
        if pattern:
            cost_filters.append(database.Cost.name.ilike(f"%{pattern}%"))
            income_filters.append(database.Income.name.ilike(f"%{pattern}%"))
            # exclude if pattern is specified. no id == 0
            exchange_filters.append(database.Exchange.id == 0)  # type: ignore

        # costs section
        cost_totals_by_currency_query: Select = (
            select(
                database.Cost.currency_id.label("currency_id"),
                func.sum(database.Cost.value).label("total"),
            )
            .where(*cost_filters)
            .group_by(database.Cost.currency_id)
            .order_by(database.Cost.currency_id)
        )

        cost_categories_totals_by_currency_query: Select = (
            select(
                # cost && cost category
                database.Cost.currency_id.label("currency_id"),
                database.CostCategory.id.label("category_id"),
                database.CostCategory.name.label("category_name"),
                # custom calculation. the `sum` of all the costs in the range
                (func.sum(database.Cost.value)).label("total"),
            )
            .join(
                database.CostCategory,
                database.Cost.category_id == database.CostCategory.id,
            )
            .where(*cost_filters)
            .group_by(database.Cost.currency_id, database.CostCategory.id)
            .order_by(database.Cost.currency_id, database.CostCategory.id)
        )

        # incomes section
        income_totals_by_currency_query: Select = (
            select(
                database.Income.currency_id.label("currency_id"),
                func.sum(database.Income.value).label("total"),
            )
            .where(*income_filters)
            .group_by(database.Income.currency_id)
            .order_by(database.Income.currency_id)
        )

        incomes_by_currency_and_source_query: Select = (
            select(
                # income
                database.Income.currency_id.label("currency_id"),
                database.Income.source.label("source"),
                # custom calculation. the `sum` of all the incomes in the range
                (func.sum(database.Income.value)).label("total"),
            )
            .where(*income_filters)
            .group_by(database.Income.currency_id, database.Income.source)
            .order_by(database.Income.currency_id, database.Income.source)
        )

        # exchange section
        exchanges_query: Select = (
            select(database.Exchange)
            .where(*exchange_filters)
            .order_by(database.Exchange.timestamp)
        )

        # perform database queries
        async with self.query.session as session:
            async with session.begin():
                try:
                    (
                        _currencies,
                        _costs_totals_by_currency,
                        _cost_totals_by_currency_and_category,
                        _incomes_totals_by_currency,
                        _income_totals_by_currency_and_source,
                        _exchanges,
                    ) = await asyncio.gather(
                        session.execute(
                            select(database.Currency).order_by(
                                desc(database.Currency.id)
                            )
                        ),
                        session.execute(cost_totals_by_currency_query),
                        session.execute(
                            cost_categories_totals_by_currency_query
                        ),
                        session.execute(income_totals_by_currency_query),
                        session.execute(incomes_by_currency_and_source_query),
                        session.execute(exchanges_query),
                    )

                except Exception as error:
                    raise errors.DatabaseError(str(error)) from error

                # Extract results inside session context
                # while session is active
                currencies = list(_currencies.scalars().all())
                costs_totals_by_currency = list(_costs_totals_by_currency)
                cost_totals_by_currency_and_category = list(
                    _cost_totals_by_currency_and_category
                )
                incomes_totals_by_currency = list(_incomes_totals_by_currency)
                income_totals_by_currency_and_source = list(
                    _income_totals_by_currency_and_source
                )
                exchanges = list(_exchanges.scalars().all())

        results: dict[int, TransactionsBasicAnalytics] = {
            currency.id: TransactionsBasicAnalytics(
                currency=Currency.from_instance(currency)
            )
            for currency in currencies
        }

        # update costs currency total
        for currency_id, total in costs_totals_by_currency:
            results[currency_id].costs.total = total

        # update incomes currency total
        for currency_id, total in incomes_totals_by_currency:
            results[currency_id].incomes.total = total

        # update cost categories totals
        for currency_id, items in itertools.groupby(
            cost_totals_by_currency_and_category,
            key=operator.attrgetter("currency_id"),
        ):
            results[currency_id].costs.categories += [
                CostsByCategory(
                    id=category_id,
                    name=category_name,
                    total=total,
                    ratio=total / results[currency_id].costs.total * 100,
                )
                for _, category_id, category_name, total in items
            ]

        # update incomes sources totals
        for currency_id, items in itertools.groupby(
            income_totals_by_currency_and_source,
            key=operator.attrgetter("currency_id"),
        ):
            results[currency_id].incomes.sources += [
                (IncomesBySource(source=source, total=total))
                for _, source, total in items
            ]

        for item in exchanges:
            results[item.from_currency_id].from_exchanges -= item.from_value
            results[item.to_currency_id].from_exchanges += item.to_value

        return tuple(results.values())

    async def daily_totals_by_currency(
        self,
        start_date: date,
        end_date: date,
        pattern: str | None = None,
    ) -> tuple[list[tuple], list[tuple]]:
        """Get daily totals grouped by (currency_name, date).

        Returns:
            Tuple of (cost_rows, income_rows) where each row is
            (currency_name, date, daily_total_cents)
        """

        # Build filters
        cost_filters = [database.Cost.timestamp.between(start_date, end_date)]
        income_filters = [
            database.Income.timestamp.between(start_date, end_date)
        ]

        if pattern:
            cost_filters.append(database.Cost.name.ilike(f"%{pattern}%"))
            income_filters.append(database.Income.name.ilike(f"%{pattern}%"))

        # Query for daily cost totals by currency
        cost_query = (
            select(
                database.Currency.name.label("currency_name"),
                database.Cost.timestamp.label("date"),
                func.sum(database.Cost.value).label("total"),
            )
            .join(
                database.Currency,
                database.Cost.currency_id == database.Currency.id,
            )
            .where(*cost_filters)
            .group_by(database.Currency.name, database.Cost.timestamp)
            .order_by(database.Currency.name, database.Cost.timestamp)
        )

        # Query for daily income totals by currency
        income_query = (
            select(
                database.Currency.name.label("currency_name"),
                database.Income.timestamp.label("date"),
                func.sum(database.Income.value).label("total"),
            )
            .join(
                database.Currency,
                database.Income.currency_id == database.Currency.id,
            )
            .where(*income_filters)
            .group_by(database.Currency.name, database.Income.timestamp)
            .order_by(database.Currency.name, database.Income.timestamp)
        )

        async with self.query.session as session:
            async with session.begin():
                cost_result = await session.execute(cost_query)
                income_result = await session.execute(income_query)

                cost_rows = [
                    (row.currency_name, row.date, row.total)
                    for row in cost_result.all()
                ]
                income_rows = [
                    (row.currency_name, row.date, row.total)
                    for row in income_result.all()
                ]

        return cost_rows, income_rows

    async def first_transaction(self) -> Transaction | None:
        """Get the earliest transaction across all transaction types."""

        CostCategoryAlias = aliased(database.CostCategory)
        CurrencyAlias = aliased(database.Currency)
        UserAlias = aliased(database.User)

        cost_query = (
            select(
                database.Cost.id.label("id"),
                database.Cost.name.label("name"),
                CostCategoryAlias.name.label("icon"),
                database.Cost.value.label("value"),
                database.Cost.timestamp.label("timestamp"),
                func.cast("cost", String).label("operation_type"),
                CurrencyAlias.name.label("currency_name"),
                CurrencyAlias.sign.label("currency_sign"),
                CurrencyAlias.id.label("currency_id"),
                UserAlias.name.label("user_name"),
            )
            .join(CurrencyAlias, database.Cost.currency)
            .join(CostCategoryAlias, database.Cost.category)
            .join(UserAlias, database.Cost.user)
        )

        income_query = (
            select(
                database.Income.id.label("id"),
                database.Income.name.label("name"),
                func.cast("🤑", String).label("icon"),
                database.Income.value.label("value"),
                database.Income.timestamp.label("timestamp"),
                func.cast("income", String).label("operation_type"),
                CurrencyAlias.name.label("currency_name"),
                CurrencyAlias.sign.label("currency_sign"),
                CurrencyAlias.id.label("currency_id"),
                UserAlias.name.label("user_name"),
            )
            .join(CurrencyAlias, database.Income.currency)
            .join(UserAlias, database.Income.user)
        )

        exchange_query = (
            select(
                database.Exchange.id.label("id"),
                func.cast("exchange", String).label("name"),
                func.cast("💱", String).label("icon"),
                database.Exchange.to_value.label("value"),
                database.Exchange.timestamp.label("timestamp"),
                func.cast("exchange", String).label("operation_type"),
                CurrencyAlias.name.label("currency_name"),
                CurrencyAlias.sign.label("currency_sign"),
                CurrencyAlias.id.label("currency_id"),
                UserAlias.name.label("user_name"),
            )
            .join(CurrencyAlias, database.Exchange.to_currency)
            .join(UserAlias, database.Exchange.user)
        )

        final_query = (
            union_all(cost_query, income_query, exchange_query)
            .order_by("timestamp")
            .order_by("id")
            .limit(1)
        )

        async with self.query.session as session:
            async with session.begin():
                result = await session.execute(final_query)
                row = result.first()

                if row is None:
                    return None

                return Transaction(
                    id=row.id,
                    name=row.name,
                    icon=row.icon,
                    value=row.value,
                    timestamp=row.timestamp,
                    operation=row.operation_type,
                    currency=Currency(
                        id=row.currency_id,
                        name=row.currency_name,
                        sign=row.currency_sign,
                    ),
                    user=row.user_name,
                )

    async def last_transaction(self) -> Transaction | None:
        """Get the most recent transaction across all transaction types."""

        CostCategoryAlias = aliased(database.CostCategory)
        CurrencyAlias = aliased(database.Currency)
        UserAlias = aliased(database.User)

        cost_query = (
            select(
                database.Cost.id.label("id"),
                database.Cost.name.label("name"),
                CostCategoryAlias.name.label("icon"),
                database.Cost.value.label("value"),
                database.Cost.timestamp.label("timestamp"),
                func.cast("cost", String).label("operation_type"),
                CurrencyAlias.name.label("currency_name"),
                CurrencyAlias.sign.label("currency_sign"),
                CurrencyAlias.id.label("currency_id"),
                UserAlias.name.label("user_name"),
            )
            .join(CurrencyAlias, database.Cost.currency)
            .join(CostCategoryAlias, database.Cost.category)
            .join(UserAlias, database.Cost.user)
        )

        income_query = (
            select(
                database.Income.id.label("id"),
                database.Income.name.label("name"),
                func.cast("🤑", String).label("icon"),
                database.Income.value.label("value"),
                database.Income.timestamp.label("timestamp"),
                func.cast("income", String).label("operation_type"),
                CurrencyAlias.name.label("currency_name"),
                CurrencyAlias.sign.label("currency_sign"),
                CurrencyAlias.id.label("currency_id"),
                UserAlias.name.label("user_name"),
            )
            .join(CurrencyAlias, database.Income.currency)
            .join(UserAlias, database.Income.user)
        )

        exchange_query = (
            select(
                database.Exchange.id.label("id"),
                func.cast("exchange", String).label("name"),
                func.cast("💱", String).label("icon"),
                database.Exchange.to_value.label("value"),
                database.Exchange.timestamp.label("timestamp"),
                func.cast("exchange", String).label("operation_type"),
                CurrencyAlias.name.label("currency_name"),
                CurrencyAlias.sign.label("currency_sign"),
                CurrencyAlias.id.label("currency_id"),
                UserAlias.name.label("user_name"),
            )
            .join(CurrencyAlias, database.Exchange.to_currency)
            .join(UserAlias, database.Exchange.user)
        )

        final_query = (
            union_all(cost_query, income_query, exchange_query)
            .order_by(desc("timestamp"))
            .order_by(desc("id"))
            .limit(1)
        )

        async with self.query.session as session:
            async with session.begin():
                result = await session.execute(final_query)
                row = result.first()

                if row is None:
                    return None
                else:
                    return Transaction(
                        id=row.id,
                        name=row.name,
                        icon=row.icon,
                        value=row.value,
                        timestamp=row.timestamp,
                        operation=row.operation_type,
                        currency=Currency(
                            id=row.currency_id,
                            name=row.currency_name,
                            sign=row.currency_sign,
                        ),
                        user=row.user_name,
                    )
