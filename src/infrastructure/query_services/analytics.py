import asyncio
import itertools
import operator
from datetime import date

from sqlalchemy import Select, String, desc, func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.domain.equity import Currency
from src.domain.transactions.value_objects import (
    CostsByCategory,
    IncomesBySource,
    Transaction,
    TransactionsBasicAnalytics,
    TransactionsFilter,
)
from src.domain.users import User
from src.infrastructure import database, dates, errors


class TransactionsAnalyticsService(database.DataAccessLayer):
    """Read-only query service for cross-entity analytics."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        super().__init__(session)

    async def transactions(  # noqa: C901
        self,
        /,
        user: User,
        filter: TransactionsFilter = TransactionsFilter(),
        **pagination_kwargs,
    ) -> tuple[tuple[Transaction, ...], int]:
        """get all the items from 'costs', 'incomes', 'exchanges'
        tables in the internal representation.
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
                func.cast(literal("cost"), String).label(
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
                func.cast(literal("\U0001f911"), String).label(
                    "icon",
                ),
                database.Income.value.label("value"),
                database.Income.timestamp.label("timestamp"),
                func.cast(literal("income"), String).label(
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
                func.cast(literal("exchange"), String).label(
                    "name",
                ),
                func.cast(literal("\U0001f4b1"), String).label(
                    "icon",
                ),
                database.Exchange.to_value.label("value"),
                database.Exchange.timestamp.label("timestamp"),
                func.cast(literal("exchange"), String).label(
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

        # execute the query and map results
        async with self._read_session() as session:
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

    async def transactions_basic_analytics(  # noqa: C901
        self,
        /,
        pattern: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> tuple[TransactionsBasicAnalytics, ...]:
        """build the transactions 'basic analytics'
        on the database level.
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
            # exclude if pattern is specified.
            # no id == 0
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
                database.Cost.currency_id.label("currency_id"),
                database.CostCategory.id.label("category_id"),
                database.CostCategory.name.label("category_name"),
                (func.sum(database.Cost.value)).label("total"),
            )
            .join(
                database.CostCategory,
                database.Cost.category_id == database.CostCategory.id,
            )
            .where(*cost_filters)
            .group_by(
                database.Cost.currency_id,
                database.CostCategory.id,
            )
            .order_by(
                database.Cost.currency_id,
                database.CostCategory.id,
            )
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
                database.Income.currency_id.label("currency_id"),
                database.Income.source.label("source"),
                (func.sum(database.Income.value)).label("total"),
            )
            .where(*income_filters)
            .group_by(
                database.Income.currency_id,
                database.Income.source,
            )
            .order_by(
                database.Income.currency_id,
                database.Income.source,
            )
        )

        # exchange section
        exchanges_query: Select = (
            select(database.Exchange)
            .where(*exchange_filters)
            .order_by(database.Exchange.timestamp)
        )

        # perform database queries
        async with self._read_session() as session:
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
                    session.execute(cost_categories_totals_by_currency_query),
                    session.execute(income_totals_by_currency_query),
                    session.execute(incomes_by_currency_and_source_query),
                    session.execute(exchanges_query),
                )

            except Exception as error:
                raise errors.DatabaseError(str(error)) from error

            # Extract results inside session context
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
                currency=Currency.model_validate(currency)
            )
            for currency in currencies
        }

        # update costs currency total
        for (
            currency_id,
            total,
        ) in costs_totals_by_currency:
            results[currency_id].costs.total = total

        # update incomes currency total
        for (
            currency_id,
            total,
        ) in incomes_totals_by_currency:
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
                for (
                    _,
                    category_id,
                    category_name,
                    total,
                ) in items
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
        """Get daily totals grouped by
        (currency_name, date).

        Returns:
            Tuple of (cost_rows, income_rows)
            where each row is
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
            .group_by(
                database.Currency.name,
                database.Cost.timestamp,
            )
            .order_by(
                database.Currency.name,
                database.Cost.timestamp,
            )
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
            .group_by(
                database.Currency.name,
                database.Income.timestamp,
            )
            .order_by(
                database.Currency.name,
                database.Income.timestamp,
            )
        )

        async with self._read_session() as session:
            cost_result = await session.execute(cost_query)
            income_result = await session.execute(income_query)

            cost_rows = [
                (
                    row.currency_name,
                    row.date,
                    row.total,
                )
                for row in cost_result.all()
            ]
            income_rows = [
                (
                    row.currency_name,
                    row.date,
                    row.total,
                )
                for row in income_result.all()
            ]

        return cost_rows, income_rows

    async def first_transaction(
        self,
    ) -> Transaction | None:
        """Get the earliest transaction across all
        transaction types.
        """

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
                func.cast(literal("cost"), String).label("operation_type"),
                CurrencyAlias.name.label("currency_name"),
                CurrencyAlias.sign.label("currency_sign"),
                CurrencyAlias.id.label("currency_id"),
                UserAlias.name.label("user_name"),
            )
            .join(CurrencyAlias, database.Cost.currency)
            .join(
                CostCategoryAlias,
                database.Cost.category,
            )
            .join(UserAlias, database.Cost.user)
        )

        income_query = (
            select(
                database.Income.id.label("id"),
                database.Income.name.label("name"),
                func.cast(literal("\U0001f911"), String).label("icon"),
                database.Income.value.label("value"),
                database.Income.timestamp.label("timestamp"),
                func.cast(literal("income"), String).label("operation_type"),
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
                func.cast(literal("exchange"), String).label("name"),
                func.cast(literal("\U0001f4b1"), String).label("icon"),
                database.Exchange.to_value.label("value"),
                database.Exchange.timestamp.label("timestamp"),
                func.cast(literal("exchange"), String).label("operation_type"),
                CurrencyAlias.name.label("currency_name"),
                CurrencyAlias.sign.label("currency_sign"),
                CurrencyAlias.id.label("currency_id"),
                UserAlias.name.label("user_name"),
            )
            .join(
                CurrencyAlias,
                database.Exchange.to_currency,
            )
            .join(UserAlias, database.Exchange.user)
        )

        final_query = (
            union_all(cost_query, income_query, exchange_query)
            .order_by("timestamp")
            .order_by("id")
            .limit(1)
        )

        async with self._read_session() as session:
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

    async def last_transaction(
        self,
    ) -> Transaction | None:
        """Get the most recent transaction across all
        transaction types.
        """

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
                func.cast(literal("cost"), String).label("operation_type"),
                CurrencyAlias.name.label("currency_name"),
                CurrencyAlias.sign.label("currency_sign"),
                CurrencyAlias.id.label("currency_id"),
                UserAlias.name.label("user_name"),
            )
            .join(CurrencyAlias, database.Cost.currency)
            .join(
                CostCategoryAlias,
                database.Cost.category,
            )
            .join(UserAlias, database.Cost.user)
        )

        income_query = (
            select(
                database.Income.id.label("id"),
                database.Income.name.label("name"),
                func.cast(literal("\U0001f911"), String).label("icon"),
                database.Income.value.label("value"),
                database.Income.timestamp.label("timestamp"),
                func.cast(literal("income"), String).label("operation_type"),
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
                func.cast(literal("exchange"), String).label("name"),
                func.cast(literal("\U0001f4b1"), String).label("icon"),
                database.Exchange.to_value.label("value"),
                database.Exchange.timestamp.label("timestamp"),
                func.cast(literal("exchange"), String).label("operation_type"),
                CurrencyAlias.name.label("currency_name"),
                CurrencyAlias.sign.label("currency_sign"),
                CurrencyAlias.id.label("currency_id"),
                UserAlias.name.label("user_name"),
            )
            .join(
                CurrencyAlias,
                database.Exchange.to_currency,
            )
            .join(UserAlias, database.Exchange.user)
        )

        final_query = (
            union_all(cost_query, income_query, exchange_query)
            .order_by(desc("timestamp"))
            .order_by(desc("id"))
            .limit(1)
        )

        async with self._read_session() as session:
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
