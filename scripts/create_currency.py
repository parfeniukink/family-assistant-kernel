"""
CLI script for creating currencies in the database.

Usage:
    python -m scripts.create_currency --name USD --sign $ --equity 100000
    python -m scripts.create_currency -n EUR -s € -e 50000
    python -m scripts.create_currency -n UAH -s ₴
"""

import argparse
import asyncio
import sys

from src.infrastructure import database, repositories


async def main() -> int:
    """Create a new currency in the database."""
    parser = argparse.ArgumentParser(
        description="Create a new currency in the database"
    )
    parser.add_argument(
        "-n", "--name", required=True, help="Currency name (e.g., USD, EUR)"
    )
    parser.add_argument(
        "-s",
        "--sign",
        required=True,
        help="Currency sign - single character (e.g., $, €, ₴)",
    )
    parser.add_argument(
        "-e",
        "--equity",
        type=int,
        default=0,
        help="Initial equity in cents (default: 0)",
    )

    args = parser.parse_args()

    # Validate sign length
    if len(args.sign) != 1:
        print(
            "Error: Currency sign must be a single character",
            file=sys.stderr,
        )
        return 1

    # Create currency
    currency = database.Currency(
        name=args.name,
        sign=args.sign,
        equity=args.equity,
    )

    try:
        repo = repositories.Currency()
        await repo.add_currency(currency)
        await repo.flush()

        print(f"\nCurrency created successfully!")
        print(f"\nName: {args.name}")
        print(f"\nSign: {args.sign}")
        print(
            f"\nEquity: {args.equity} cents "
            f"({args.equity / 100:.2f} {args.name})"
        )

    except Exception as e:
        print(f"Error creating currency: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
else:
    raise SystemExit("Sorry, this module can not be imported")
