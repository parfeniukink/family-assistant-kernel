"""
NBU (National Bank of Ukraine) API client for fetching exchange rates.

NBU API returns rates as "how many UAH per 1 unit of foreign currency".
For example, if USD rate is 42.0295, it means 1 USD = 42.0295 UAH.

# ─────────────────────────────────────────────────────────
HTTP RESOURCE: https://bank.gov.ua/NBU_Exchange/exchange_site
# ─────────────────────────────────────────────────────────
QUERY PARAMS
json: Set to any value to get JSON response
date: Date in `YYYYMMDD` format

# ─────────────────────────────────────────────────────────
RESPONSE
# ─────────────────────────────────────────────────────────
[
     {
       "r030": 941,
       "txt": "Сербський динар",
       "rate": 0.42395,
       "cc": "RSD",
       "exchangedate": "01.01.2026",
       "special": null
     },
     {
       "r030": 944,
       "txt": "Азербайджанський манат",
       "rate": 24.9107,
       "cc": "AZN",
       "exchangedate": "01.01.2026",
       "special": null
     },
    ...
]
"""

import asyncio
from collections.abc import AsyncGenerator, Iterable
from datetime import date, datetime
from typing import Final, Self

import httpx
from loguru import logger
from pydantic import field_validator

from src.infrastructure import PublicData

BASE_URL: Final = (
    "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange"
)


# TODO: Take the structure from the domain layer
#       and return to the Application layer
class NBURate(PublicData):
    """Represents a single exchange rate from NBU API."""

    cc: str
    rate: float
    exchangedate: datetime

    @field_validator("exchangedate", mode="before")
    def normalize_date(cls, value: str) -> datetime:
        return datetime.strptime(value, "%d.%m.%Y")


class Client:
    """Client for NBU API with built-in rate limiting and retry logic."""

    def __init__(
        self,
        max_concurrent: int = 5,
        request_timeout: float = 30.0,
        retry_delay: float = 3.0,
        max_retries: int = 3,
        batch_delay: float = 1.0,
    ):
        """
        Initialize NBU client.

        Args:
            max_concurrent: Maximum concurrent requests
            request_timeout: Timeout for each request in seconds
            retry_delay: Base delay for retries in seconds
            max_retries: Maximum number of retries per request
            batch_delay: Delay between batches in seconds
        """
        self.max_concurrent = max_concurrent
        self.request_timeout = request_timeout
        self.retry_delay = retry_delay
        self.max_retries = max_retries
        self.batch_delay = batch_delay

        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._rate_limit_event = asyncio.Event()
        self._rate_limit_event.set()  # Start without rate limiting
        self._client: httpx.AsyncClient | None = None
        self._completed_count = 0

    async def __aenter__(self) -> Self:
        self._client = httpx.AsyncClient(
            timeout=self.request_timeout,
            limits=httpx.Limits(
                max_connections=self.max_concurrent,
                max_keepalive_connections=self.max_concurrent,
            ),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # WARNING: This function is too complex!!!
    async def _fetch_single_rate(  # noqa: C901
        self, target_date: date, currency_code: str
    ) -> NBURate | None:
        """Fetch exchange rate for a single date."""

        if not self._client:
            raise RuntimeError(
                "Client not initialized. Use 'async with' context manager."
            )

        params = {
            "date": target_date.strftime("%Y%m%d"),
            "json": "1",
        }

        for attempt in range(self.max_retries + 1):
            # Wait if rate limited
            await self._rate_limit_event.wait()

            try:
                async with self._semaphore:
                    response = await self._client.get(BASE_URL, params=params)
                    response.raise_for_status()
                    data = response.json()

                if not data:
                    return None

                for item in data:
                    if item["cc"] == currency_code:
                        return NBURate.model_validate(item)
                return None

            except httpx.TimeoutException as error:
                if attempt < self.max_retries:
                    wait_time = self.retry_delay
                    logger.warning(
                        f"Timeout fetching {target_date} "
                        f"(attempt {attempt + 1}/{self.max_retries + 1}), "
                        f"retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"Error fetching {target_date} after "
                        f"{self.max_retries + 1} attempts: {error}"
                    )
                    return None

            except httpx.HTTPStatusError as error:
                # Handle rate limiting (429)
                if error.response.status_code == 429:
                    if attempt < self.max_retries:
                        # Pause ALL requests
                        self._rate_limit_event.clear()

                        # Check Retry-After header
                        retry_after = error.response.headers.get("Retry-After")
                        if retry_after:
                            try:
                                wait_time = float(retry_after)
                            except ValueError:
                                wait_time = self.retry_delay * (2**attempt)
                        else:
                            # Exponential backoff
                            wait_time = self.retry_delay * (2**attempt)

                        logger.warning(
                            "Rate limited (429)! Pausing ALL requests for "
                            f"{wait_time:.1f}s (triggered by {target_date})"
                        )
                        await asyncio.sleep(wait_time)

                        # Resume all requests
                        self._rate_limit_event.set()
                        logger.info("Rate limit cleared, resuming requests...")
                    else:
                        logger.error(
                            f"Rate limit exceeded for {target_date} after "
                            f"{self.max_retries + 1} attempts"
                        )
                        return None

                # Handle gateway timeout (504)
                elif error.response.status_code == 504:
                    if attempt < self.max_retries:
                        wait_time = self.retry_delay
                        logger.warning(
                            f"Gateway timeout (504) for {target_date} "
                            f"(attempt {attempt + 1}/{self.max_retries + 1}), "
                            f"retrying in {wait_time}s..."
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(
                            f"Gateway timeout for {target_date} "
                            f"after {self.max_retries + 1} attempts"
                        )
                        return None
                else:
                    logger.error(f"HTTP error fetching {target_date}: {error}")
                    return None

            except Exception as error:
                logger.error(
                    f"Unexpected error fetching {target_date}: {error}"
                )
                return None

        return None

    async def fetch_rates(
        self, dates: Iterable[date], currency_code: str
    ) -> AsyncGenerator[NBURate | None, None]:
        """
        Fetch exchange rates for multiple dates.

        Args:
            dates: Dates to fetch rates for
            currency_code: ISO 4217 currency code (e.g., "USD", "EUR")

        Yields:
            NBURate objects or None for failed requests
        """
        dates_list = list(dates)
        if not dates_list:
            return

        # Create all tasks
        tasks = {
            asyncio.create_task(self._fetch_single_rate(dt, currency_code)): dt
            for dt in dates_list
        }

        # Poll for completed tasks
        while tasks:
            done, pending = await asyncio.wait(
                tasks.keys(),
                timeout=1.0,
                return_when=asyncio.FIRST_COMPLETED,
            )

            logger.debug(
                "Processing Exchange Rates:\t"
                f"[{len(done)}] done, [{len(pending)}] pending"
            )

            # Yield results from completed tasks
            for task in done:
                result = await task
                yield result
                tasks.pop(task)
                self._completed_count += 1

                # Batch delay
                if self._completed_count % self.max_concurrent == 0 and tasks:
                    logger.debug(
                        f"Processed {self._completed_count} requests, "
                        f"pausing {self.batch_delay}s..."
                    )
                    await asyncio.sleep(self.batch_delay)
