"""
test currencies.
"""

import httpx
import pytest
from fastapi import status

from src import http
from src.infrastructure import database, repositories


@pytest.mark.use_db
async def test_currencies_list(
    client: httpx.AsyncClient, currencies: list[database.Currency]
):
    response: httpx.Response = await client.get("/currencies")

    assert response.status_code == status.HTTP_200_OK, response.json()
    assert len(response.json()["result"]) == len(currencies)


@pytest.mark.use_db
async def test_currency_creation(client: httpx.AsyncClient):
    payload: dict = http.CurrencyCreateBody(name="USD", sign="$").model_dump()
    response: httpx.Response = await client.post("/currencies", json=payload)

    total_currencies: int = await repositories.Currency().count(
        database.Currency
    )

    assert response.status_code == status.HTTP_201_CREATED, response.json()
    assert total_currencies == 1
