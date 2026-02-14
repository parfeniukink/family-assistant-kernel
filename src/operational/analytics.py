"""
this module includes high-level operations to deal with transactions analytics.

instead of putting this to the ``./transactions.py``
this is separated to have cleaner code.
"""

from datetime import date, timedelta

from loguru import logger

from src.domain import exchange_rates
from src.domain import transactions as domain
from src.domain.equity import EquityRepository
from src.infrastructure import database, dates
from src.integrations import nbu


async def ensure_exchange_rates(start_date: date, end_date: date) -> None:
    """Sync database Exchange Rates with NBU rates.

    DISASSEMBLED
    (1) currencies <- select from database
    (2) for each currency: missing_dates <- start_date..end_date
            that have no exchange rates in database
    (3) for each currency: rates <- nbu.Client.fetch_rates(missing_dates)
    (4) rates -> insert into database

    NOTES
    (1) Each fetched rate saved to the database in separate transaction
    """

    repo = exchange_rates.ExchangeRateRepository()
    equity_repo = EquityRepository()

    # Phase 1: reads — no transaction needed
    currencies = await equity_repo.currencies()
    currency_codes = [c.name for c in currencies if c.name != "UAH"]

    for currency_code in currency_codes:
        existing_dates = await repo.get_existing_dates(
            currency_code, start_date, end_date
        )

        all_dates = set()
        current = start_date
        while current <= end_date:
            all_dates.add(current)
            current += timedelta(days=1)

        missing_dates = all_dates - existing_dates

        if missing_dates:
            logger.warning(
                f"{len(missing_dates)} exchange rates are missing..."
            )
        else:
            logger.info(
                f"All {len(existing_dates)} exchange rates exist in database"
            )

        async with nbu.Client() as client:
            async for rate in client.fetch_rates(missing_dates, currency_code):
                if rate is None:
                    logger.warning("Missing Rate")
                    continue
                else:
                    async with database.transaction():
                        candidate = database.ExchangeRate(
                            cc_from="UAH",  # base currency
                            cc_to=rate.cc,
                            rate=rate.rate,
                            date=rate.exchangedate,
                        )
                        await repo.add_rate(candidate)

                    logger.success(
                        f"Exchange Rate {rate.exchangedate} {rate.rate} "
                        "saved to the database"
                    )


async def compute_total_ratio_usd(
    start_date: date, end_date: date, pattern: str | None = None
) -> float:
    """Sum all costs/incomes converted to USD, return ratio.

    Conversion formula:
        amount_in_usd = (amount_cents * nbu_rate_for_currency)
                        / nbu_rate_for_usd

    UAH is the base currency with implicit rate of 1.0.
    """

    tx_repo = domain.TransactionRepository()
    rate_repo = exchange_rates.ExchangeRateRepository()

    # Get daily totals
    cost_rows, income_rows = await tx_repo.daily_totals_by_currency(
        start_date, end_date, pattern
    )

    # Load exchange rates
    rates = await rate_repo.get_rates(start_date, end_date)

    # Build lookup: (currency_code, date) -> rate
    rate_lookup: dict[tuple[str, date], float] = {}
    for rate in rates:
        rate_lookup[(rate.cc_to, rate.date)] = rate.rate

    # Convert costs to USD
    total_costs_usd = 0.0
    for currency_name, tx_date, total_cents in cost_rows:
        usd_amount = _convert_to_usd(
            currency_name, tx_date, total_cents, rate_lookup
        )
        total_costs_usd += usd_amount

    # Convert incomes to USD
    total_incomes_usd = 0.0
    for currency_name, tx_date, total_cents in income_rows:
        usd_amount = _convert_to_usd(
            currency_name, tx_date, total_cents, rate_lookup
        )
        total_incomes_usd += usd_amount

    # Calculate ratio
    if total_incomes_usd and total_costs_usd:
        return total_costs_usd / total_incomes_usd * 100
    elif not total_costs_usd:
        return 0.0
    else:
        return 100.0


def _convert_to_usd(
    currency_name: str,
    tx_date: date,
    amount_cents: int,
    rate_lookup: dict[tuple[str, date], float],
) -> float:
    """Convert amount to USD using NBU rates.

    Formula: amount_in_usd = (amount * rate_for_currency) / rate_for_usd

    For UAH: rate is implicitly 1.0 (base currency)
    """

    if currency_name == "USD":
        # Already in USD
        return float(amount_cents)

    # Get USD rate for the date
    usd_rate = rate_lookup.get(("USD", tx_date))
    if usd_rate is None:
        # Fallback: use closest available USD rate or default
        usd_rate = _get_fallback_rate("USD", tx_date, rate_lookup)

    if currency_name == "UAH":
        # UAH to USD: amount / usd_rate
        return float(amount_cents) / usd_rate if usd_rate else 0.0

    # Other currency to USD
    currency_rate = rate_lookup.get((currency_name, tx_date))
    if currency_rate is None:
        currency_rate = _get_fallback_rate(currency_name, tx_date, rate_lookup)

    if not currency_rate or not usd_rate:
        return 0.0

    # Convert: (amount * currency_rate_in_uah) / usd_rate_in_uah
    return (float(amount_cents) * currency_rate) / usd_rate


def _get_fallback_rate(
    currency_code: str,
    target_date: date,
    rate_lookup: dict[tuple[str, date], float],
) -> float | None:
    """Get closest available rate for a currency within the same month."""

    # Filter rates for this currency within the same month
    currency_rates = [
        (d, r)
        for (c, d), r in rate_lookup.items()
        if c == currency_code
        and d.year == target_date.year
        and d.month == target_date.month
    ]

    if not currency_rates:
        return None

    # Find closest date
    closest = min(currency_rates, key=lambda x: abs((x[0] - target_date).days))
    return closest[1]


async def transactions_basic_analytics(
    period: domain.AnalyticsPeriod | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    pattern: str | None = None,
) -> domain.BasicAnalyticsResult:
    """return basic transaction analytics with currency-independent ratio."""

    if start_date is not None and end_date is not None:
        if period is not None:
            raise ValueError(
                "you can't specify dates and period simultaneously"
            )
        _start_date = start_date
        _end_date = end_date
    elif pattern is not None and start_date is None and end_date is None:
        # Pattern-only search: use current month as default range
        _start_date = dates.get_first_date_of_current_month()
        _end_date = date.today()
    elif any((start_date, end_date)):
        raise ValueError("the range requires both dates to be specified")
    else:
        if period == "current-month":
            _start_date = dates.get_first_date_of_current_month()
            _end_date = date.today()
        elif period == "previous-month":
            _start_date, _end_date = dates.get_previous_month_range()
        else:
            raise ValueError(f"Unavailable period: {period}")

    # Get per-currency analytics
    instances = (
        await domain.TransactionRepository().transactions_basic_analytics(
            start_date=_start_date, end_date=_end_date, pattern=pattern
        )
    )

    # Ensure exchange rates are cached
    try:
        await ensure_exchange_rates(_start_date, _end_date)
    except Exception as error:
        logger.error(error)
        logger.warning(
            "Can't fetch some currencies from NBU for dates "
            "Please try later"
        )
        total_ratio = 0.0
    else:
        # Compute currency-independent total ratio
        total_ratio = await compute_total_ratio_usd(
            _start_date, _end_date, pattern
        )

    return domain.BasicAnalyticsResult(
        per_currency=instances,
        total_ratio=total_ratio,
    )
