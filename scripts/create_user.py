"""
CLI script for creating users with JWT authentication support.

Usage:
    python -m scripts.create_user --username john --password secret123
    python -m scripts.create_user -u john -p secret123
"""

import argparse
import asyncio
import sys

from src.infrastructure import database, repositories, security


async def main() -> int:
    """Create a new user in the database."""
    parser = argparse.ArgumentParser(
        description="Create a new user with JWT authentication support"
    )
    parser.add_argument(
        "-u", "--username", required=True, help="Username for the new user"
    )
    parser.add_argument(
        "-p", "--password", required=True, help="Password for the new user"
    )

    args = parser.parse_args()

    # Hash password with Argon2 (OWASP recommended)
    password_hash = security.hash_password(args.password)

    # Create user
    user = database.User(name=args.username, password_hash=password_hash)

    try:
        repo = repositories.User()
        await repo.add_user(user)
        await repo.flush()

        print(f"\nUser created successfully!")
        print(f"Username: {args.username}")
        print(f"Password: hashed with Argon2")

    except Exception as e:
        print(f"Error creating user: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
else:
    raise SystemExit("Sorry, this module can not be imported")
