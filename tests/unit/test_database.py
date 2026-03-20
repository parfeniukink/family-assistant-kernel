import asyncio
import random
import string

import pytest

from src.infrastructure import database, errors, repositories


@pytest.mark.use_db
async def test_database_transactions_separate_success():
    repo = repositories.User()
    first_user = await repo.add_user(
        candidate=database.User(name=random.choice(string.ascii_letters))
    )

    await repo.flush()
    assert first_user.id is not None, "user id is not populated after flushing"

    await repo.add_user(
        candidate=database.User(name=random.choice(string.ascii_letters))
    )
    await repo.flush()

    users_total: int = await repositories.User().count(database.User)

    assert users_total == 2, f"received {users_total} users. expected 2"


@pytest.mark.use_db
async def test_database_transactions_gathered_success():
    repo = repositories.User()
    tasks = [
        repo.add_user(
            candidate=database.User(name=random.choice(string.ascii_letters))
        )
        for _ in range(2)
    ]
    await asyncio.gather(*tasks)
    await repo.flush()

    users_total: int = await repositories.User().count(database.User)

    assert users_total == 2, f"received {users_total} users. expected 2"


@pytest.mark.use_db
async def test_database_transactions_rollback():
    """check if session transaction works correctly.

    notes:
        if error was raise at the same transaction block user should not
        exist in the database.
    """

    with pytest.raises(errors.DatabaseError):
        async with database.transaction() as session:
            await repositories.User(session=session).add_user(
                candidate=database.User(
                    name="john",
                )
            )

            raise Exception("Some exception")

    repo = repositories.User()
    await repo.add_user(
        candidate=database.User(
            name="john",
        )
    )
    await repo.flush()

    john = await repositories.User().user_by_id(1)

    assert john.name == "john"
