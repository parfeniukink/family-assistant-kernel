"""
since the application is created to be used along with SPA in the browser,
we are going to send notifications to the frontend on regular HTTP Request.

notifications are 'super-low' priority so they are removed right after
client requested notifications.
"""

import asyncio
from typing import Literal

from src import domain
from src.infrastructure import Cache, database, errors, repositories

# aliases
pretty_money = domain.transactions.pretty_money


async def notify(
    user_id: int,
    topic: Literal["big_costs", "incomes"],
    notification: domain.notifications.Notification,
):

    if topic not in domain.notifications.Notifications.model_fields.keys():
        raise errors.BaseError(
            message=f"notifications topic {topic} is not available"
        )

    async with Cache() as cache:
        try:
            results: dict = await cache.get(
                namespace="fambb_notifications", key=str(user_id)
            )
        except errors.NotFoundError:
            notifications = domain.notifications.Notifications()
        else:
            notifications = domain.notifications.Notifications(**results)

        topic_notifications: list[domain.notifications.Notification] = getattr(
            notifications, topic
        )
        topic_notifications.append(notification)

        # update cache instance
        await cache.set(
            namespace="fambb_notifications",
            key=str(user_id),
            value=notifications.model_dump(),
        )


async def user_notifications_count(
    user: domain.users.User,
) -> int:
    """Return total notification count without consuming."""

    async with Cache() as cache:
        try:
            results: dict = await cache.get(
                namespace="fambb_notifications",
                key=str(user.id),
            )
        except errors.NotFoundError:
            return 0
        else:
            notifications = domain.notifications.Notifications(**results)
            return len(notifications.big_costs) + len(notifications.incomes)


async def user_notifications(
    user: domain.users.User,
) -> domain.notifications.Notifications:
    """

    WORKFLOW
        1. retrieve notifications from the cache
        2. remove notifications in the cache
    """

    async with Cache() as cache:
        try:
            results: dict = await cache.get(
                namespace="fambb_notifications", key=str(user.id)
            )
        except errors.NotFoundError:
            notifications = domain.notifications.Notifications()
        else:
            notifications = domain.notifications.Notifications(**results)

            # erase notifications
            await cache.delete(
                namespace="fambb_notifications", key=str(user.id)
            )

        return notifications


async def notify_about_big_cost(cost: database.Cost):
    """add notification if threshold in the confiuration
    is above of the value of the cost
    """

    users = repositories.User().by_cost_threshold_notification(cost=cost)

    async for user in users:
        asyncio.create_task(
            notify(
                user_id=user.id,
                topic="big_costs",
                notification=domain.notifications.Notification(
                    message=(
                        f"{cost.name}: {pretty_money(cost.value)} "
                        f"{cost.currency.sign}"
                    ),
                    level="\U0001f4c9",
                ),
            )
        )


async def notify_about_income(income: database.Income):

    user = await repositories.User().excluding(income.user_id)

    asyncio.create_task(
        notify(
            user_id=user.id,
            topic="incomes",
            notification=domain.notifications.Notification(
                message=(
                    f"{income.name}: {pretty_money(income.value)} "
                    f"{income.currency.sign}"
                ),
                level="\U0001f4c8",
            ),
        )
    )
