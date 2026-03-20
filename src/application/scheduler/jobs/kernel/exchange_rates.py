from datetime import date

from loguru import logger

from src.application.analytics import ensure_exchange_rates
from src.domain.jobs import register_job_type
from src.infrastructure.query_services import TransactionsAnalyticsService


@register_job_type("kernel", name="Exchange Rates Sync", interval_minutes=240)
async def sync_exchange_rates() -> None:
    """Ensures exchange rates exist for all dates between
    the first transaction and today.

    NOTES
    (1) Runs every 4 hours
    """

    first = await TransactionsAnalyticsService().first_transaction()

    if first is None:
        logger.info("No transactions yet — skipping exchange rates sync")
        return
    else:
        await ensure_exchange_rates(first.timestamp, date.today())
        logger.success("Exchange Rates are ensured")
