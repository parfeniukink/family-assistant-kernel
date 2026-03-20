"""
this package includes high-level tests for currency exchange operatinos
"""

import asyncio

import httpx
import pytest
from fastapi import status

from src.infrastructure import database, repositories


# ==================================================
# tests for not authorized
# ==================================================
@pytest.mark.use_db
async def test_exchange_fetch_anonymous(anonymous: httpx.AsyncClient):
    response = await anonymous.get("/transactions/exchange")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.use_db
async def test_exchange_add_anonymous(
    anonymous: httpx.AsyncClient,
):
    response = await anonymous.post("/transactions/exchange", json={})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.use_db
async def test_exchange_delete_anonymous(
    anonymous: httpx.AsyncClient,
):
    response = await anonymous.delete("/transactions/exchange/1")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ==================================================
# tests for authorized user
# ==================================================
@pytest.mark.use_db
async def test_exchange_fetch(client: httpx.AsyncClient, exchange_factory):
    """test response paginated by default."""

    items: list[database.Exchange] = await exchange_factory(n=15)

    response1: httpx.Response = await client.get("/transactions/exchange")
    response1_data = response1.json()

    response2: httpx.Response = await client.get(
        "/transactions/exchange", params={"context": response1_data["context"]}
    )
    response2_data = response2.json()

    total = await repositories.Exchange().count(database.Exchange)

    assert total == len(items)

    assert response1.status_code == status.HTTP_200_OK
    assert len(response1_data["result"]) == 10
    assert response1_data["context"] == 10
    assert response1_data["left"] == 5

    assert len(response2_data["result"]) == 5
    assert response2_data["context"] == 15
    assert response2_data["left"] == 0


@pytest.mark.use_db
async def test_exchange_add(client: httpx.AsyncClient, currencies):
    response = await client.post(
        "/transactions/exchange",
        json={
            "fromCurrencyId": 1,
            "fromValue": 10.00,
            "toCurrencyId": 2,
            "toValue": 20.00,
        },
    )

    total = await repositories.Exchange().count(database.Exchange)

    tasks = (
        repositories.Currency().currency(id_=1),
        repositories.Currency().currency(id_=2),
    )

    from_currency, to_currency = await asyncio.gather(*tasks)

    assert response.status_code == status.HTTP_201_CREATED, response.json()
    assert total == 1
    assert from_currency.equity == currencies[0].equity - 1000
    assert to_currency.equity == currencies[1].equity + 2000


@pytest.mark.use_db
async def test_exchange_delete(
    client: httpx.AsyncClient, currencies, exchange_factory
):
    item, *_ = await exchange_factory(n=1)
    response = await client.delete(f"/transactions/exchange/{item.id}")

    currency_from, currency_to = await asyncio.gather(
        repositories.Currency().currency(id_=1),
        repositories.Currency().currency(id_=2),
    )
    total = await repositories.Exchange().count(database.Exchange)

    assert total == 0
    assert response.status_code == status.HTTP_204_NO_CONTENT, response.json()
    assert currency_from.equity == currencies[0].equity + item.from_value
    assert currency_to.equity == currencies[1].equity - item.to_value


# ==================================================
# tests for validation
# ==================================================
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": None},
        {"name": 12},
        {"another-field": "proper string"},
    ],
)
@pytest.mark.use_db
async def test_exchange_add_unprocessable(
    client: httpx.AsyncClient, payload: dict
):
    response = await client.post("/transactions/exchange", json=payload)

    total = await repositories.Exchange().count(database.Exchange)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert total == 0
