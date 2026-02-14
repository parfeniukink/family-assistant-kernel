from typing import Final

import httpx
import pytest
import respx
from fastapi import status

from src import domain
from src.infrastructure import database
from src.integrations import monobank
from tests.utils import read_json

BASE_URL: Final = "/transactions/lookup-missing"


@pytest.mark.skip("Monobank is not integrated yet")
@pytest.mark.use_db
async def test_lookup_missing_UNAUTHORIZED(anonymous: httpx.AsyncClient):
    response: httpx.Response = await anonymous.post(BASE_URL)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.skip("Monobank is not integrated yet")
@pytest.mark.use_db
async def test_lookup_missing_NO_API_KEY_IN_SETTINGS(
    client: httpx.AsyncClient,
):
    response: httpx.Response = await client.post(BASE_URL)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.skip("Monobank is not integrated yet")
@pytest.mark.use_db
@respx.mock
async def test_monobank_sync(john, client: httpx.AsyncClient):
    mock_response_personal_info = read_json(
        "response/monobank_personal_info.json"
    )

    personal_info_route = respx.get(monobank.PERSONAL_INFO_URL).mock(
        return_value=httpx.Response(
            status.HTTP_200_OK, json=mock_response_personal_info
        )
    )

    mock_response_statement = read_json("response/monobank_statement.json")
    statement_route = respx.route(
        url__regex=rf"{monobank.STATEMENTS_URL}/[\w+]"
    ).mock(
        return_value=httpx.Response(
            status.HTTP_200_OK, json=mock_response_statement
        )
    )

    # patch cache ``get`` method to make sure that
    # it must be check before saving transactions to prevent duplicates
    await domain.users.UserRepository().update_user(
        id_=john.id, monobank_api_key="mock api key"
    )

    async with database.transaction():
        await domain.users.UserRepository().update_user(
            id_=john.id, monobank_api_key="mock api key"
        )

    response: httpx.Response = await client.post(f"{BASE_URL}/sync")

    assert response.status_code == status.HTTP_204_NO_CONTENT, response.json()
    assert personal_info_route.call_count == 1
    assert statement_route.call_count == 1
