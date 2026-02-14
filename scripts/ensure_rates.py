"""
CLI script for populating exchange rates into the database

Usage:
    python -m scripts.ensure_rates
"""

import argparse
import asyncio
import sys
from datetime import date, datetime

from src.operational.analytics import ensure_exchange_rates


async def main() -> int:
    """Fetch exchange rates from NBU and save them to the database.

    NOTES
    first and last costs dates are used as a range
    """

    parser = argparse.ArgumentParser(
        description="Fetch Exchange Rates from NBU and save them to the database"
    )
    parser.add_argument(
        "-s",
        "--start",
        action="store",
        required=True,
        help="Start date in the range",
    )
    parser.add_argument(
        "-e",
        "--end",
        action="store_const",
        required=False,
        help="End date in the range (today by default)",
    )
    args = parser.parse_args()

    # Validation
    if not args.end:
        _end_date: date = date.today()
    else:
        _end_date = datetime.strptime(args.end, "%Y-%m-%d").date()

    _start_date: date = datetime.strptime(args.start, "%Y-%m-%d").date()

    # Requests and Database Updates
    try:
        await ensure_exchange_rates(start_date=_start_date, end_date=_end_date)
    except Exception as e:
        print(f"Error fetching exchange rates: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
else:
    raise SystemExit("Sorry, this module can not be imported")
