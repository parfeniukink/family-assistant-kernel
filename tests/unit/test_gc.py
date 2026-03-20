from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from src.application.scheduler.jobs.kernel.gc import garbage_collect
from src.domain.users import User, UserConfiguration


def _user(id_: int, gc_retention_days: int = 3) -> User:
    return User(
        id=id_,
        name=f"user-{id_}",
        configuration=UserConfiguration(
            gc_retention_days=gc_retention_days,
        ),
    )


@pytest.mark.asyncio
async def test_gc_uses_minimum_retention_across_users():
    mock_news = AsyncMock()
    mock_news.delete_stale_items.return_value = 5

    mock_user_repo = AsyncMock()
    mock_user_repo.all_users.return_value = [
        _user(1, gc_retention_days=5),
        _user(2, gc_retention_days=2),
        _user(3, gc_retention_days=10),
    ]

    with (
        patch(
            "src.application.scheduler.jobs.kernel.gc" ".repositories.News",
            return_value=mock_news,
        ),
        patch(
            "src.application.scheduler.jobs.kernel.gc" ".repositories.User",
            return_value=mock_user_repo,
        ),
    ):
        await garbage_collect()

    expected_cutoff = date.today() - timedelta(days=2)
    mock_news.delete_stale_items.assert_awaited_once_with(
        before_date=expected_cutoff
    )
    mock_news.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_gc_default_retention():
    mock_news = AsyncMock()
    mock_news.delete_stale_items.return_value = 0

    mock_user_repo = AsyncMock()
    mock_user_repo.all_users.return_value = [_user(1)]

    with (
        patch(
            "src.application.scheduler.jobs.kernel.gc" ".repositories.News",
            return_value=mock_news,
        ),
        patch(
            "src.application.scheduler.jobs.kernel.gc" ".repositories.User",
            return_value=mock_user_repo,
        ),
    ):
        await garbage_collect()

    expected_cutoff = date.today() - timedelta(days=3)
    mock_news.delete_stale_items.assert_awaited_once_with(
        before_date=expected_cutoff
    )


@pytest.mark.asyncio
async def test_gc_skips_when_no_users():
    mock_user_repo = AsyncMock()
    mock_user_repo.all_users.return_value = []

    with patch(
        "src.application.scheduler.jobs.kernel.gc" ".repositories.User",
        return_value=mock_user_repo,
    ):
        await garbage_collect()


@pytest.mark.asyncio
async def test_gc_raises_on_error():
    mock_news = AsyncMock()
    mock_news.delete_stale_items.side_effect = RuntimeError("db gone")

    mock_user_repo = AsyncMock()
    mock_user_repo.all_users.return_value = [_user(1)]

    with (
        patch(
            "src.application.scheduler.jobs.kernel.gc" ".repositories.News",
            return_value=mock_news,
        ),
        patch(
            "src.application.scheduler.jobs.kernel.gc" ".repositories.User",
            return_value=mock_user_repo,
        ),
    ):
        with pytest.raises(RuntimeError, match="db gone"):
            await garbage_collect()
