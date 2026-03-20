"""
test notifications that are happening on events.
"""

import asyncio

import httpx
import pytest
from fastapi import status

from src.infrastructure import database, repositories
from tests.mock import Cache


@pytest.mark.use_db
async def test_user_NOTIFIED_about_big_cost(
    currencies, cost_categories, client, john, client_marry
):
    """
    WORKFLOW
        1. John update ``notify_cost_threshold`` configuration
        2. Marry creates the cost with value ABOVE (greater)
            the `notify_cost_threshold`
        3. wait for notification to be added to the cache in the background
        4. check notification object is ADDED to the cache
    """

    await client.patch(
        "/identity/users/configuration", json={"notifyCostThreshold": 199.9}
    )

    add_cost_response: httpx.Response = await client_marry.post(
        "/transactions/costs",
        json={"name": "PS5", "value": 200, "currencyId": 1, "categoryId": 1},
    )

    assert (
        add_cost_response.status_code == status.HTTP_201_CREATED
    ), add_cost_response.json()

    await asyncio.sleep(0.1)
    cache_len_after_creating_cost = len(
        Cache._data[f"fambb_notifications:{john.id}"]["big_costs"]
    )

    notifications_response = await client.get("/notifications")

    assert (
        notifications_response.status_code == status.HTTP_200_OK
    ), notifications_response.json()
    assert cache_len_after_creating_cost == 1, Cache._data
    assert Cache._data == {}


@pytest.mark.use_db
async def test_user_NOT_NOTIFIED_about_big_cost(
    currencies, cost_categories, client, john, client_marry
):
    """
    WORKFLOW
        1. John update ``notify_cost_threshold`` configuration
        2. Marry creates the cost with value BELOW the `notify_cost_threshold`
        4. check notification object is NOT ADDED to the cache
    """

    await client.patch(
        "/identity/users/configuration", json={"notifyCostThreshold": 200.01}
    )

    add_cost_response: httpx.Response = await client_marry.post(
        "/transactions/costs",
        json={"name": "PS5", "value": 200, "currencyId": 1, "categoryId": 1},
    )

    await asyncio.sleep(0.1)
    john_notificaitons = Cache._data.get(f"fambb_notifications:{john.id}")

    notifications_response = await client.get("/notifications")

    assert (
        add_cost_response.status_code == status.HTTP_201_CREATED
    ), add_cost_response.json()
    assert (
        notifications_response.status_code == status.HTTP_200_OK
    ), notifications_response.json()
    assert john_notificaitons is None, john_notificaitons
    assert Cache._data == {}


@pytest.mark.use_db
async def test_user_notified_about_big_cost_after_update(
    currencies, cost_categories, client, john, marry, client_marry
):
    """
    WORKFLOW
        1. set John's cost notification threshold
        2. create the Cost for Marry
        3. Marry updates the cost
        4. check notification object in the cache
    """

    repo = repositories.Cost()
    _, cost = await asyncio.gather(
        client.patch(
            "/identity/users/configuration",
            json={"notify_cost_threshold": 200},
        ),
        repo.add_cost(
            database.Cost(
                name="water",
                value=200,
                user_id=marry.id,
                currency_id=1,
                category_id=1,
            )
        ),
    )
    await repo.flush()

    add_cost_response: httpx.Response = await client_marry.patch(
        f"/transactions/costs/{cost.id}", json={"value": 300}
    )

    await asyncio.sleep(0.1)
    cache_len_after_creating_cost = len(
        Cache._data[f"fambb_notifications:{john.id}"]["big_costs"]
    )

    notifications_response = await client.get("/notifications")

    assert (
        add_cost_response.status_code == status.HTTP_200_OK
    ), add_cost_response.json()
    assert (
        notifications_response.status_code == status.HTTP_200_OK
    ), notifications_response.json()
    assert cache_len_after_creating_cost == 1, Cache._data
    assert Cache._data == {}


@pytest.mark.use_db
async def test_user_notified_about_income(
    currencies, client, john, client_marry
):
    """
    WORKFLOW
        1. Marry adds an income
        2. wait for notification to be added to the cache in the background
        3. check notification object is added to the cache
    """

    add_cost_response: httpx.Response = await client_marry.post(
        "/transactions/incomes",
        json={"name": "jb", "value": 20, "currencyId": 1, "source": "revenue"},
    )

    await asyncio.sleep(0.1)
    cache_len_after_creating_cost = len(
        Cache._data[f"fambb_notifications:{john.id}"]["incomes"]
    )

    notifications_response = await client.get("/notifications")

    assert (
        add_cost_response.status_code == status.HTTP_201_CREATED
    ), add_cost_response.json()
    assert (
        notifications_response.status_code == status.HTTP_200_OK
    ), notifications_response.json()
    assert cache_len_after_creating_cost == 1, Cache._data
    assert Cache._data == {}
