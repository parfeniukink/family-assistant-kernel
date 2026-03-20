"""
migration details:
    - create users manually. John - 1, Marry - 2
    - create currencies manually - USD - 1, UAH - 2
    - run script

sql queries:
    insert into users (name,token) values ('John', 'secret');
    insert into users (name,token) values ('Marry', 'secret');
    insert into currencies (name,sign,equity) values ('USD', '$', xxx);
    insert into currencies (name,sign,equity) values ('UAH', '#', xxx);
"""

import asyncio
import sqlite3
from datetime import datetime

from src.infrastructure import database, repositories

connection = sqlite3.connect("../db.sqlite3")

COST_CATEGORIES_MAPPER = {
    "🍽 Food": {
        "old_id": 1,
    },
    "🥗 Restaurants": {
        "old_id": 1,
    },
    "🍔 Food delivery": {
        "old_id": 2,
    },
    "🚌 Roads": {
        "old_id": 3,
    },
    "👚 Clothes": {
        "old_id": 4,
    },
    "🚙 Car": {
        "old_id": 5,
    },
    "⛽️ Fuel": {
        "old_id": 6,
    },
    "🪴 Household": {
        "old_id": 8,
    },
    "🤝 Rents": {
        "old_id": 9,
    },
    "💳 Services": {
        "old_id": 10,
    },
    "🏝 Leisure": {
        "old_id": 11,
    },
    "💻 Technical stuff": {
        "old_id": 12,
    },
    "📚 Education": {
        "old_id": 13,
    },
    "🎁 Gifts": {
        "old_id": 14,
    },
    "📦 Other": {
        "old_id": 15,
    },
    "♥️ Health": {
        "old_id": 16,
    },
    "💼 Business": {
        "old_id": 17,
    },
    "💸 Debts": {
        "old_id": 18,
    },
    "🏠️ House": {
        "old_id": 19,
    },
    "💸 Taxes": {
        "old_id": 20,
    },
}


async def migrate_cost_categories():
    cost_category_names: list[tuple[str, ...]] = connection.execute(
        "SELECT name from categories ORDER BY id"
    ).fetchall()
    cost_category_candidates = [
        database.CostCategory(name=data[0]) for data in cost_category_names
    ]

    repo = repositories.Cost()
    for candidate in cost_category_candidates:
        await repo.add_cost_category(candidate)
    await repo.flush()


async def migrate_costs():
    costs_payloads: list[tuple[str, ...]] = connection.execute(
        "SELECT name,value,date,user_id,category_id,currency_id from costs ORDER BY id"
    ).fetchall()

    candidates = [
        database.Cost(
            name=data[0],
            value=data[1],
            timestamp=datetime.strptime(data[2], "%Y-%m-%d"),
            user_id=data[3],
            category_id=data[4],
            currency_id=data[5],
        )
        for data in costs_payloads
    ]

    repo = repositories.Cost()
    for candidate in candidates:
        await repo.add_cost(candidate)
    await repo.flush()


async def migrate_incomes():
    available_sources = ("revenue", "other", "gift", "debt")

    def source_mapper(old_value: str):
        if old_value.lower() not in available_sources:
            raise ValueError(f"Value {old_value} is not recognized")
        else:
            return old_value.lower()

    costs_payloads: list[tuple[str, ...]] = connection.execute(
        "SELECT name,value,source,date,user_id,currency_id from incomes ORDER BY id"
    ).fetchall()

    candidates = [
        database.Income(
            name=data[0],
            value=data[1],
            source=source_mapper(data[2]),
            timestamp=datetime.strptime(data[3], "%Y-%m-%d").date(),
            user_id=data[4],
            currency_id=data[5],
        )
        for data in costs_payloads
    ]

    repo = repositories.Income()
    for candidate in candidates:
        await repo.add_income(candidate)
    await repo.flush()


async def migrate_exchanges():
    payloads: list[tuple[str, ...]] = connection.execute(
        "SELECT source_value,destination_value,source_currency_id,destination_currency_id,date,user_id from currency_exchange ORDER BY id"
    ).fetchall()

    candidates = [
        database.Exchange(
            from_value=data[0],
            to_value=data[1],
            from_currency_id=data[2],
            to_currency_id=data[3],
            timestamp=datetime.strptime(data[4], "%Y-%m-%d").date(),
            user_id=data[5],
        )
        for data in payloads
    ]

    repo = repositories.Exchange()
    for candidate in candidates:
        await repo.add_exchange(candidate)
    await repo.flush()


async def migrate():
    await migrate_cost_categories()
    await migrate_costs()
    await migrate_incomes()
    await migrate_exchanges()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(migrate()))
else:
    raise SystemExit("Sorry, this module can not be imported")
