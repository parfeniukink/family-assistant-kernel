"""CLI script for setting user password hash in the database.

Usage:
    python -m scripts.set_password --id 2 --password admin
    python -m scripts.set_password -i 2 -p admin
"""

import argparse
import asyncio
import sys

from src.infrastructure import repositories, security


async def main() -> int:
    """Update user password hash in the database."""
    parser = argparse.ArgumentParser(
        description="Set user password hash in the database"
    )
    parser.add_argument(
        "-i", "--id", required=True, type=int, help="User ID to update"
    )
    parser.add_argument(
        "-p", "--password", required=True, help="New password for the user"
    )

    args = parser.parse_args()

    try:
        # Hash password with Argon2
        password_hash = security.hash_password(args.password)

        # Verify user exists
        repo = repositories.User()
        try:
            await repo.user_by_id(args.id)
        except Exception:
            print(
                f"Error: User with ID {args.id} not found",
                file=sys.stderr,
            )
            return 1

        # Update user password
        await repo.update_user(args.id, password_hash=password_hash)
        await repo.flush()

        print(f"\nPassword updated successfully for user ID {args.id}!")

    except Exception as e:
        print(f"Error updating password: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
else:
    raise SystemExit("Sorry, this module can not be imported")
