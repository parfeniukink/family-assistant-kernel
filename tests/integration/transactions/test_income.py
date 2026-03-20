"""
this package includes high-level tests for income operatinos
"""

import asyncio
from datetime import timedelta

import httpx
import pytest
from fastapi import status

from src import domain, http
from src.infrastructure import database, repositories


# ==================================================
# tests for not authorized
# ==================================================
@pytest.mark.use_db
async def test_income_fetch_anonymous(anonymous: httpx.AsyncClient):
    response = await anonymous.get("/transactions/incomes")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.use_db
async def test_income_create_anonymous(
    anonymous: httpx.AsyncClient,
):
    response = await anonymous.post("/transactions/incomes", json={})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ==================================================
# tests for authorized user
# ==================================================
@pytest.mark.use_db
async def test_incomes_fetch(client: httpx.AsyncClient, income_factory):
    """test response paginated by default."""

    incomes: list[database.Income] = await income_factory(n=15)

    response1: httpx.Response = await client.get("/transactions/incomes")
    response1_data = response1.json()
    response2: httpx.Response = await client.get(
        "/transactions/incomes", params={"context": response1_data["context"]}
    )
    response2_data = response2.json()

    total = await repositories.Income().count(database.Income)

    assert total == len(incomes)

    assert response1.status_code == status.HTTP_200_OK
    assert len(response1_data["result"]) == 10
    assert response1_data["context"] == 10
    assert response1_data["left"] == 5

    assert len(response2_data["result"]) == 5
    assert response2_data["context"] == 15
    assert response2_data["left"] == 0


@pytest.mark.use_db
async def test_income_add(client: httpx.AsyncClient, currencies):
    response = await client.post(
        "/transactions/incomes",
        json={
            "name": "office job",
            "value": 100.0,  # not in cents
            "source": "revenue",
            "currencyId": 1,
        },
    )

    total = await repositories.Income().count(database.Income)

    currency: database.Currency = await repositories.Currency().currency(id_=1)

    assert response.status_code == status.HTTP_201_CREATED, response.json()
    assert total == 1
    assert currency.equity == currencies[0].equity + 10000


@pytest.mark.use_db
async def test_income_update_safe(
    client: httpx.AsyncClient, currencies, income_factory
):
    """test operations that should not change the equity."""

    income, *_ = await income_factory(n=1)
    body = http.IncomeUpdateBody(
        name="".join((income.name, "some salt")),
        timestamp=income.timestamp - timedelta(days=3),
    )

    response = await client.patch(
        f"/transactions/incomes/{income.id}", json=body.json_body()
    )

    currency: database.Currency = await repositories.Currency().currency(id_=1)

    updated_instance = await repositories.Income().income(id_=income.id)

    assert response.status_code == status.HTTP_200_OK, response.json()
    assert currency.equity == currencies[0].equity
    for attr in {"name", "timestamp"}:
        assert getattr(updated_instance, attr) == getattr(body, attr)


@pytest.mark.use_db
async def test_income_update_only_value_increased(
    client: httpx.AsyncClient, currencies, income_factory
):
    income, *_ = await income_factory(n=1)
    new_value = domain.transactions.pretty_money(income.value) + 100
    response = await client.patch(
        f"/transactions/incomes/{income.id}", json={"value": new_value}
    )

    currency: database.Currency = await repositories.Currency().currency(id_=1)
    updated_instance = await repositories.Income().income(id_=income.id)

    assert response.status_code == status.HTTP_200_OK, response.json()
    assert currency.equity == currencies[0].equity + 10000
    assert updated_instance.value == income.value + 10000


@pytest.mark.use_db
async def test_income_update_only_currency(
    client: httpx.AsyncClient, currencies, income_factory
):
    income, *_ = await income_factory(n=1)
    new_currency_id = 2
    response = await client.patch(
        f"/transactions/incomes/{income.id}",
        json={"currency_id": new_currency_id},
    )

    src_currency, dst_currency = await asyncio.gather(
        repositories.Currency().currency(id_=income.currency_id),
        repositories.Currency().currency(id_=new_currency_id),
    )

    updated_instance = await repositories.Income().income(id_=income.id)

    assert response.status_code == status.HTTP_200_OK, response.json()
    assert src_currency.equity == currencies[0].equity - income.value
    assert dst_currency.equity == currencies[1].equity + income.value
    assert updated_instance.currency_id == new_currency_id


@pytest.mark.use_db
async def test_income_update_currency_and_value(
    client: httpx.AsyncClient, currencies, income_factory
):
    income, *_ = await income_factory(n=1)
    payload: dict = {
        "currency_id": 2,
        "value": domain.transactions.pretty_money(income.value) + 100,
    }
    response = await client.patch(
        f"/transactions/incomes/{income.id}", json=payload
    )

    src_currency, dst_currency = await asyncio.gather(
        repositories.Currency().currency(id_=income.currency_id),
        repositories.Currency().currency(id_=payload["currency_id"]),
    )

    updated_instance = await repositories.Income().income(id_=income.id)

    assert response.status_code == status.HTTP_200_OK, response.json()
    assert src_currency.equity == currencies[0].equity - income.value
    assert dst_currency.equity == income.value + 10000
    assert updated_instance.currency_id == payload["currency_id"]


# ==================================================
# tests for validation
# ==================================================
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": None},
        {"name": 12},
        {"anotherField": "proper string"},
    ],
)
@pytest.mark.use_db
async def test_income_add_unprocessable(
    client: httpx.AsyncClient, payload: dict
):
    response = await client.post("/transactions/incomes", json=payload)

    total = await repositories.Income().count(database.Income)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert total == 0
