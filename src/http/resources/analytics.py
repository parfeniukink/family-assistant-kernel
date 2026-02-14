from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src import domain
from src import operational as op
from src.infrastructure import ResponseMulti

from ..contracts import (
    Equity,
    TransactionAnalyticsResponse,
    TransactionBasicAnalytics,
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/equity")
async def equity(
    _: domain.users.User = Depends(op.authorize),
) -> ResponseMulti[Equity]:
    """expose the ``equity``, related to each currency."""

    return ResponseMulti[Equity](
        result=[
            Equity.from_instance(item)
            for item in await domain.equity.EquityRepository().currencies()
        ]
    )


@router.get("/transactions/basic")
async def transaction_analytics_basic(
    period: Annotated[
        domain.transactions.AnalyticsPeriod | None,
        Query(description="specified period instead of start and end dates"),
    ] = None,
    start_date: Annotated[
        date | None,
        Query(
            description="the start date of transaction in the analytics",
            alias="startDate",
        ),
    ] = None,
    end_date: Annotated[
        date | None,
        Query(
            description="the end date of transaction in the analytics",
            alias="endDate",
        ),
    ] = None,
    pattern: Annotated[
        str | None,
        Query(
            description="the pattern to filter results",
            alias="pattern",
        ),
    ] = None,
    _: domain.users.User = Depends(op.authorize),
) -> TransactionAnalyticsResponse:
    """basic analytics that supports a set of some filters.

    WORKFLOW:
        - user can specify either start date & end date or the 'period'.
        - user can specify the pattern which is NOT CASE-SENSITIVE to filter
            by that 'pattern' in 'cost name' or 'income name'.

    POSSIBLE ERRORS:
        - nothing is specified
        - 'period' and 'date' are specified
        - only a single date is specified (no range)
        - unrecognized period is specified

    NOTES:
        if the 'pattern' is specified you WON'T see EXCHANGES in your analytics
    """

    result = await op.transactions_basic_analytics(
        period, start_date, end_date, pattern
    )

    return TransactionAnalyticsResponse(
        result=[
            TransactionBasicAnalytics.from_instance(instance)
            for instance in result.per_currency
        ],
        total_ratio=result.total_ratio,
    )
