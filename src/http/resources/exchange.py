import asyncio

from fastapi import APIRouter, Body, Depends, status

from src import application as op
from src import domain
from src.infrastructure import (
    OffsetPagination,
    Response,
    ResponseMultiPaginated,
    database,
    get_offset_pagination_params,
    repositories,
)

from ..contracts import Exchange, ExchangeCreateBody

router = APIRouter(
    prefix="/transactions/exchange",
    tags=["Transactions", "Exchange"],
)


# WARNING: deprecated
@router.get("")
async def exchanges(
    user: domain.users.User = Depends(op.authorize),
    pagination: OffsetPagination = Depends(get_offset_pagination_params),
) -> ResponseMultiPaginated[Exchange]:
    """get incomes."""

    tasks = (
        op.get_currency_exchanges(
            user_id=user.id,
            offset=pagination.context,
            limit=pagination.limit,
        ),
        repositories.Exchange().count(database.Exchange),
    )

    items, total = await asyncio.gather(*tasks)

    if items:
        context: int = pagination.context + len(items)
        left: int = total - context
    else:
        context = 0
        left = 0

    return ResponseMultiPaginated[Exchange](
        result=[Exchange.from_instance(item) for item in items],
        context=context,
        left=left,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_exchange(
    user: domain.users.User = Depends(op.authorize),
    body: ExchangeCreateBody = Body(...),
) -> Response[Exchange]:
    """add exchange. side effect: equity updated for 2 currencies."""

    item: database.Exchange = await op.currency_exchange(
        from_value=body.from_value_in_cents,
        to_value=body.to_value_in_cents,
        timestamp=body.timestamp,
        from_currency_id=body.from_currency_id,
        to_currency_id=body.to_currency_id,
        user_id=user.id,
    )

    return Response[Exchange](result=Exchange.from_instance(item))


@router.get("/{exchange_id}", status_code=status.HTTP_200_OK)
async def get_exchange(
    exchange_id: int,
    _: domain.users.User = Depends(op.authorize),
) -> Response[Exchange]:
    """get exchange."""

    instance = await repositories.Exchange().exchange(id_=exchange_id)

    return Response[Exchange](result=Exchange.from_instance(instance))


@router.delete("/{exchange_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exchange(
    exchange_id: int,
    _: domain.users.User = Depends(op.authorize),
) -> None:
    """delete exchange. side effect: the equity is decreased."""

    await op.delete_currency_exchange(item_id=exchange_id)
