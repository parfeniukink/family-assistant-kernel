from typing import Any

from src.domain.users import User
from src.infrastructure import repositories


async def user_retrieve(id_: int) -> User:
    return await repositories.User().user_by_id(id_=id_)


async def update_user_configuration(user: User, **values: Any) -> User:
    """Update user configuration.

    FLOW
    (1) Dispatch configurations that are related to background jobs
        to re-schedule them
    (2) Update user information in database
    """

    repo = repositories.User()

    if "gc_retention_days" in values:
        raise NotImplementedError

    await repo.update_user(user.id, **values)
    await repo.flush()

    return await repo.user_by_id(user.id)
