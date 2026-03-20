from fastapi import APIRouter, Depends

from src import application as op
from src import domain
from src.http.contracts import Transaction, get_transactions_detail_filter
from src.infrastructure import (
    OffsetPagination,
    ResponseMultiPaginated,
    get_offset_pagination_params,
)
from src.infrastructure.query_services import TransactionsAnalyticsService

router = APIRouter(prefix="/transactions", tags=["Transactions"])


@router.get("")
async def transactions(
    filter: domain.transactions.TransactionsFilter = Depends(
        get_transactions_detail_filter
    ),
    pagination: OffsetPagination = Depends(get_offset_pagination_params),
    user: domain.users.User = Depends(op.authorize),
) -> ResponseMultiPaginated[Transaction]:
    """transactions list. includes costs, incomes and exchanges.


    NOTES

    (1) the returned ``total`` value is based on applied filters.
    if the currency is specified - ``total`` might be changed
    so you can rely on data properly.

    (2) if the ``cost_category_id`` is provided - pagination is skipped
    """

    (
        items,
        total,
    ) = await TransactionsAnalyticsService().transactions(
        user=user,
        filter=filter,
        offset=pagination.context,
        limit=pagination.limit,
    )

    if items:
        context: int = pagination.context + len(items)
        left: int = total - context
    else:
        context = 0
        left = 0

    return ResponseMultiPaginated[Transaction](
        result=[Transaction.from_instance(item) for item in items],
        context=context,
        left=left,
    )


# @router.post("/lookup-missing")
# async def lookup_missing_transactions(
#     start_date: Annotated[
#         date,
#         Query(
#             description=(
#                 "the start date of transaction in the analytics. "
#                 "default value is the first day of the current year"
#             ),
#             alias="startDate",
#         ),
#     ],
#     end_date: Annotated[
#         date,
#         Query(
#             description="the end date of transaction in the analytics",
#             alias="endDate",
#         ),
#     ],
#     user: domain.users.User = Depends(op.authorize),
# ) -> None:
#     """Looking for missing transactions
#     with all available banks integrations.
#     """

#     await op.lookup_missing_transactions(user, start_date, end_date)
