"""
this module includes high-level operations to deal with transactions analytics.

instead of putting this to the ``./transactions.py``
this is separated to have cleaner code.
"""

from datetime import date, timedelta

from loguru import logger

from src.domain import transactions as domain
from src.infrastructure import database, dates, repositories
from src.infrastructure.query_services import TransactionsAnalyticsService
from src.integrations import nbu


async def ensure_exchange_rates(start_date: date, end_date: date) -> None:
    """Sync database Exchange Rates with NBU rates.

    DISASSEMBLED
    (1) currencies <- select from database
    (2) for each currency: missing_dates <- start_date..end_date
            that have no exchange rates in database
    (3) for each currency: rates <- nbu.Client.fetch_rates(missing_dates)
    (4) rates -> insert into database
    (5) for still-missing dates: find closest rate from DB
        and persist it for each missing date

    NOTES
    (1) Each fetched rate saved to the database in separate transaction
    """

    repo = repositories.ExchangeRate()
    currency_repo = repositories.Currency()

    # Phase 1: reads — no transaction needed
    currencies = await currency_repo.currencies()
    currency_codes = [c.name for c in currencies if c.name != "UAH"]

    all_dates: set[date] = set()
    current = start_date
    while current <= end_date:
        all_dates.add(current)
        current += timedelta(days=1)

    for currency_code in currency_codes:
        existing_dates = await repo.get_existing_dates(
            currency_code, start_date, end_date
        )

        missing_dates = all_dates - existing_dates

        if missing_dates:
            logger.warning(
                f"{len(missing_dates)} exchange rates are missing..."
            )
        else:
            logger.info(
                f"All {len(existing_dates)} exchange rates "
                "exist in database"
            )

        # Phase 2: try to fetch from NBU
        fetched_dates: set[date] = set()
        async with nbu.Client() as client:
            async for rate in client.fetch_rates(missing_dates, currency_code):
                if rate is None:
                    logger.warning("Missing Rate")
                    continue

                rate_repo = repositories.ExchangeRate()
                candidate = database.ExchangeRate(
                    cc_from="UAH",
                    cc_to=rate.cc,
                    rate=rate.rate,
                    date=rate.exchangedate,
                )
                await rate_repo.add_rate(candidate)
                await rate_repo.flush()
                fetched_dates.add(rate.exchangedate.date())

                logger.success(
                    f"Exchange Rate {rate.exchangedate} "
                    f"{rate.rate} saved to the database"
                )

        # Phase 3: fallback — fill still-missing dates
        # with the closest available rate from the DB
        still_missing = missing_dates - fetched_dates
        if not still_missing:
            continue

        closest = await repo.get_closest_rate(currency_code, start_date)
        if closest is None:
            logger.warning(f"No rates at all for {currency_code} in DB")
            continue

        logger.info(
            f"Filling {len(still_missing)} missing "
            f"{currency_code} dates with closest rate "
            f"({closest.date}: {closest.rate})"
        )
        for missing_date in still_missing:
            rate_repo = repositories.ExchangeRate()
            candidate = database.ExchangeRate(
                cc_from="UAH",
                cc_to=currency_code,
                rate=closest.rate,
                date=missing_date,
                source="fallback",
            )
            await rate_repo.add_rate(candidate)
            await rate_repo.flush()


async def compute_total_ratio_usd(
    start_date: date, end_date: date, pattern: str | None = None
) -> float:
    """Sum all costs/incomes converted to USD, return ratio.

    Conversion formula:
        amount_in_usd = (amount_cents * nbu_rate_for_currency)
                        / nbu_rate_for_usd

    UAH is the base currency with implicit rate of 1.0.
    """

    tx_service = TransactionsAnalyticsService()

    # Get daily totals
    cost_rows, income_rows = await tx_service.daily_totals_by_currency(
        start_date, end_date, pattern
    )

    # Ensure exchange rates are cached (fetches from NBU + fallback)
    await ensure_exchange_rates(start_date, end_date)

    # Load exchange rates
    rate_repo = repositories.ExchangeRate()
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
    """Get closest available rate for a currency from all loaded rates."""

    # Filter all rates for this currency (no month restriction)
    currency_rates = [
        (d, r) for (c, d), r in rate_lookup.items() if c == currency_code
    ]

    if not currency_rates:
        return None

    # Find closest date
    closest = min(
        currency_rates,
        key=lambda x: abs((x[0] - target_date).days),
    )
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
        await TransactionsAnalyticsService().transactions_basic_analytics(
            start_date=_start_date,
            end_date=_end_date,
            pattern=pattern,
        )
    )

    # Compute currency-independent total ratio
    try:
        total_ratio = await compute_total_ratio_usd(
            _start_date, _end_date, pattern
        )
    except Exception as error:
        logger.error(error)
        logger.warning(
            "Can't compute total ratio. " "Exchange rates may be unavailable."
        )
        total_ratio = 0.0

    return domain.BasicAnalyticsResult(
        per_currency=instances,
        total_ratio=total_ratio,
    )
