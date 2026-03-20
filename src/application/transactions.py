from datetime import date
from typing import cast

from src import domain
from src.infrastructure import database, errors, repositories


# ==================================================
# COSTS SECTION
# ==================================================
async def get_costs(
    limit: int,
    offset: int,
    user_id: int | None = None,
) -> tuple[database.Cost, ...]:
    """get paginated costs. proxy values to the repository."""

    items = tuple(
        [
            item
            async for item in (
                repositories.Cost().costs(
                    user_id=user_id, offset=offset, limit=limit
                )
            )
        ]
    )

    return items


async def add_cost(
    name: str,
    value: int,
    timestamp: date,
    currency_id: int,
    category_id: int,
    user_id: int,
) -> database.Cost:

    async with database.transaction() as session:
        cost_repo = repositories.Cost(session=session)
        currency_repo = repositories.Currency(session=session)
        instance = await cost_repo.add_cost(
            candidate=database.Cost(
                name=name,
                value=value,
                timestamp=timestamp,
                user_id=user_id,
                currency_id=currency_id,
                category_id=category_id,
            )
        )
        await currency_repo.decrease_equity(currency_id, value)

    return await repositories.Cost().cost(id_=instance.id)


async def update_cost(cost_id: int, **values) -> database.Cost:
    """update the cost with additional validations.

    params:
        ``cost_id``  stands for the candidate identifier
        ``values``  includes update payload candidate

    workflow:
        get cost instance or 404
        if value is the same - remove it from the payload.
        update the ``cost``
        update ``equity``
    """

    duplicates = set()
    cost: database.Cost = await repositories.Cost().cost(id_=cost_id)

    for attr, value in values.items():
        try:
            if getattr(cost, attr) == value:
                duplicates.add(attr)
        except AttributeError as error:
            raise errors.DatabaseError(
                f"'costs' table does not have '{attr}' column"
            ) from error

    for attr in duplicates:
        del values[attr]

    if not values:
        raise errors.BadRequestError("nothing to update")

    async with database.transaction() as session:
        cost_repo = repositories.Cost(session=session)
        currency_repo = repositories.Currency(session=session)
        await cost_repo.update_cost(cost, **values)

        # add equity adjustments
        if (new_currency_id := values.get("currency_id")) is not None:
            if (value := values.get("value")) is not None:
                await currency_repo.increase_equity(
                    cost.currency.id, cost.value
                )
                await currency_repo.decrease_equity(new_currency_id, value)
            else:
                await currency_repo.increase_equity(
                    cost.currency.id, cost.value
                )
                await currency_repo.decrease_equity(
                    new_currency_id, cost.value
                )
        else:
            if (value := values.get("value")) is not None:
                await currency_repo.decrease_equity(
                    cost.currency_id, value - cost.value
                )

    return await repositories.Cost().cost(id_=cost_id)


async def delete_cost(cost_id: int) -> None:
    """update the cost with additional validations.

    params:
        ``cost_id``  stands for the candidate identifier

    workflow:
        get cost instance or 404
        delete the ``cost``
        increase the ``equity``
    """

    cost = await repositories.Cost().cost(id_=cost_id)

    async with database.transaction() as session:
        cost_repo = repositories.Cost(session=session)
        currency_repo = repositories.Currency(session=session)
        await cost_repo.delete(database.Cost, candidate_id=cost_id)
        await currency_repo.increase_equity(cost.currency_id, cost.value)


# ==================================================
# INCOMES SECTION
# ==================================================
async def get_incomes(
    limit: int,
    offset: int,
    user_id: int | None = None,
) -> tuple[database.Income, ...]:
    """get paginated incomes. proxy values to the repository."""

    items = tuple(
        [
            item
            async for item in (
                repositories.Income().incomes(
                    user_id=user_id, offset=offset, limit=limit
                )
            )
        ]
    )

    return items


async def add_income(
    name: str,
    value: int,
    timestamp: date,
    source: domain.transactions.IncomeSource,
    currency_id: int,
    user_id: int,
) -> database.Income:
    """add another yet income and change the currency equity."""

    async with database.transaction() as session:
        income_repo = repositories.Income(session=session)
        currency_repo = repositories.Currency(session=session)
        instance = await income_repo.add_income(
            candidate=database.Income(
                name=name,
                value=value,
                timestamp=timestamp,
                source=source,
                currency_id=currency_id,
                user_id=user_id,
            )
        )
        await currency_repo.increase_equity(currency_id, value)

    return await repositories.Income().income(id_=instance.id)


async def update_income(income_id: int, **values) -> database.Income:
    """update the income with additional validations.

    params:
        ``income_id``  stands for the candidate identifier
        ``values``  includes update payload candidate

    workflow:
        get income instance or 404
        if value is the same - remove it from the payload.
        update the ``income``
        update ``equity``
    """

    duplicates = set()
    income = await repositories.Income().income(id_=income_id)

    for attr, value in values.items():
        try:
            if getattr(income, attr) == value:
                duplicates.add(attr)
        except AttributeError as error:
            raise errors.DatabaseError(
                f"'incomes' table does not have '{attr}' column"
            ) from error

    for attr in duplicates:
        del values[attr]

    if not values:
        raise errors.BadRequestError("nothing to update")

    async with database.transaction() as session:
        income_repo = repositories.Income(session=session)
        currency_repo = repositories.Currency(session=session)
        await income_repo.update_income(income, **values)

        # add equity adjustments
        if (new_currency_id := values.get("currency_id")) is not None:
            await currency_repo.decrease_equity(
                income.currency.id, income.value
            )
            if (value := values.get("value")) is not None:
                await currency_repo.increase_equity(new_currency_id, value)
            else:
                await currency_repo.increase_equity(
                    new_currency_id, income.value
                )
        else:
            if (value := values.get("value")) is not None:
                await currency_repo.increase_equity(
                    income.currency_id, value - income.value
                )

    return await repositories.Income().income(id_=income_id)


async def delete_income(income_id: int):
    """update the income with additional validations.

    params:
        ``income_id``  stands for the candidate identifier

    workflow:
        get income instance or 404
        delete the ``income``
        decrease ``equity``
    """

    income = await repositories.Income().income(id_=income_id)

    async with database.transaction() as session:
        income_repo = repositories.Income(session=session)
        currency_repo = repositories.Currency(session=session)
        await income_repo.delete(database.Income, candidate_id=income_id)
        await currency_repo.decrease_equity(income.currency_id, income.value)


# ==================================================
# CURRENCY EXCHANGE SECTION
# ==================================================
async def get_currency_exchanges(
    limit: int,
    offset: int,
    user_id: int | None = None,
) -> tuple[database.Exchange, ...]:
    """get paginated costs. proxy values to the repository."""

    items = tuple(
        [
            item
            async for item in (
                repositories.Exchange().exchanges(
                    user_id=user_id, offset=offset, limit=limit
                )
            )
        ]
    )

    return items


async def currency_exchange(
    from_value: int,
    to_value: int,
    timestamp: date,
    from_currency_id: int,
    to_currency_id: int,
    user_id: int,
) -> database.Exchange:
    """exchange the currency.

    params:
        ``from_value``  how much you give
        ``to_value``  how much you receive
        ``from_currency_id``  source currency id
        ``to_currency_id``  destination currency id

    workflow:
        create an exchange rate database record
        update equity for both currencies
    """

    async with database.transaction() as session:
        exchange_repo = repositories.Exchange(session=session)
        currency_repo = repositories.Currency(session=session)
        instance = await exchange_repo.add_exchange(
            candidate=database.Exchange(
                from_value=from_value,
                to_value=to_value,
                timestamp=timestamp,
                from_currency_id=from_currency_id,
                to_currency_id=to_currency_id,
                user_id=user_id,
            )
        )
        await currency_repo.decrease_equity(
            currency_id=from_currency_id, value=from_value
        )
        await currency_repo.increase_equity(
            currency_id=to_currency_id, value=to_value
        )

    return await repositories.Exchange().exchange(id_=instance.id)


async def delete_currency_exchange(item_id: int) -> None:
    """update the income with additional validations.

    params:
        ``item_id``  stands for the candidate identifier

    workflow:
        get item or 404
        delete item
        updaate equity
    """

    item = await repositories.Exchange().exchange(id_=item_id)

    async with database.transaction() as session:
        exchange_repo = repositories.Exchange(session=session)
        currency_repo = repositories.Currency(session=session)
        await exchange_repo.delete(database.Exchange, candidate_id=item_id)
        await currency_repo.increase_equity(
            item.from_currency_id, item.from_value
        )
        await currency_repo.decrease_equity(item.to_currency_id, item.to_value)


# ==================================================
# SHORTCUTS SECTION
# ==================================================
async def add_cost_shortcut(
    user: domain.users.User,
    name: str,
    value: int | None,
    currency_id: int,
    category_id: int,
) -> database.CostShortcut:
    repo = repositories.Cost()

    try:
        last_cost_shortcut: database.CostShortcut = (
            await repo.last_cost_shortcut(user.id)
        )
        assert (
            last_cost_shortcut.ui_position_index is not None
        ), "`cost_shortcuts.ui_position_index` is not set"
        ui_position_index = last_cost_shortcut.ui_position_index + 1
    except errors.NotFoundError:
        ui_position_index = 1

    write_repo = repositories.Cost()
    instance: database.CostShortcut = await write_repo.add_cost_shortcut(
        candidate=database.CostShortcut(
            name=name,
            value=value,
            timestamp=date.today(),
            currency_id=currency_id,
            category_id=category_id,
            user_id=user.id,
            ui_position_index=ui_position_index,
        )
    )
    await write_repo.flush()

    return await repo.cost_shortcut(user_id=user.id, id_=instance.id)


async def get_cost_shortcuts(
    user: domain.users.User,
) -> tuple[database.CostShortcut, ...]:
    """return all the cost shortcuts for the user."""

    items = tuple(
        [
            item
            async for item in (
                repositories.Cost().cost_shortcuts(user_id=user.id)
            )
        ]
    )

    return items


async def delete_cost_shortcut(
    user: domain.users.User, shortcut_id: int
) -> None:
    """Delete Cost Shortcut Command.

    FLOW
    (1) Delete item from the database
    (2) Recalculate positions
    """
    repo = repositories.Cost()
    await repo.delete(database.CostShortcut, candidate_id=shortcut_id)
    await repo.rebuild_ui_positions(user.id)
    await repo.flush()


async def apply_cost_shortcut(
    user: domain.users.User,
    shortcut_id: int,
    value: int | None,
    date_override: date | None = None,
) -> database.Cost:
    """try to apply the cost shortcut."""

    shortcut: database.CostShortcut = await repositories.Cost().cost_shortcut(
        user_id=user.id, id_=shortcut_id
    )

    if shortcut.value is None and value is None:
        raise ValueError("The value for the cost shortcut is not specified.")
    else:
        cost: database.Cost = await add_cost(
            name=shortcut.name,
            value=cast(int, shortcut.value or value),
            timestamp=date_override or date.today(),
            currency_id=shortcut.currency_id,
            category_id=shortcut.category_id,
            user_id=user.id,
        )

    return await repositories.Cost().cost(id_=cost.id)


# ==================================================
# DEBUG TRANSACTIONS SECTION
# ==================================================
# async def lookup_missing_transactions(
#     user: domain.users.User, start_date: date, end_date: date
# ):
#     # (1) get monobank transactions
#     if user.configuration.monobank_api_key is None:
#         raise errors.UnprocessableRequestError("No API Keys were found")

#     transactions = await monobank.get_transactions(
#         api_key=user.configuration.monobank_api_key,
#         start=start_date,
#         end=end_date,
#     )

#     # Get simified Monobank transactions
#     _ = [
#         {
#             "currency_code": tx.currency_code,
#             "description": tx.description or "",
#             "amount": abs(tx.amount),  # positive value
#         }
#         for tx in transactions
#     ]

#     # Placeholder: you will implement the db comparison logic yourself
#     # missed = await op.find_missed_costs(user.id, simplified)

#     return {"missed": {}}
