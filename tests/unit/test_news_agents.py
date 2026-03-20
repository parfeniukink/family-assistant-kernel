import json
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.news import _normalize
from src.domain.news.value_objects import ArticleCandidate

# ── _normalize (sync, pure) ──


def test_normalize_basic():
    assert _normalize("Hello World") == "hello world"


def test_normalize_collapses_whitespace():
    assert _normalize("  foo   bar  ") == "foo bar"


def test_normalize_empty_string():
    assert _normalize("") == ""


def test_normalize_already_normal():
    assert _normalize("already normal") == "already normal"


# ── helpers ──


def _candidate(
    title: str = "Article",
    description: str = "desc",
    url: str = "http://x",
) -> ArticleCandidate:
    return ArticleCandidate(title=title, description=description, url=url)


# ── ingest_articles ──


async def test_ingest_articles_skips_all_duplicates():
    """All candidates match existing titles → no agent call."""

    with (
        patch("src.application.news.repositories") as mock_repos,
        patch("src.application.news.news_agent") as mock_agent,
    ):
        news_repo = AsyncMock()
        news_repo.cached_seen_urls.return_value = {"http://x"}
        mock_repos.News.return_value = news_repo

        from src.application.news import ingest_articles

        result = await ingest_articles(
            candidates=[_candidate(title="Existing Article")],
            source_name="test",
            user_id=1,
        )

    assert result is None
    mock_agent.run.assert_not_called()


async def test_ingest_articles_calls_agent():
    """New candidates → agent is called with correct context."""

    with (
        patch("src.application.news.repositories") as mock_repos,
        patch("src.application.news.news_agent") as mock_agent,
    ):
        news_repo = AsyncMock()
        news_repo.recent_titles.return_value = []
        news_repo.today_news_items.return_value = []
        mock_repos.News.return_value = news_repo

        user = MagicMock()
        user.configuration.news_filter_prompt = "keep tech"
        user.configuration.news_preference_profile = "likes AI"
        user_repo = AsyncMock()
        user_repo.user_by_id.return_value = user
        mock_repos.User.return_value = user_repo

        mock_agent.run = AsyncMock(return_value=MagicMock(output="Done"))

        from src.application.news import ingest_articles

        result = await ingest_articles(
            candidates=[
                _candidate(title="New Article", url="http://new"),
            ],
            source_name="test-feed",
            user_id=1,
        )

    assert result is None
    mock_agent.run.assert_awaited_once()

    # Verify context passed to agent
    call_kwargs = mock_agent.run.call_args.kwargs
    ctx = call_kwargs["deps"]
    assert ctx.source_name == "test-feed"
    assert ctx.filter_prompt == "keep tech"
    assert ctx.preference_profile == "likes AI"


async def test_ingest_deduplicates_within_batch():
    """Two candidates with identical title are collapsed into one."""

    with (
        patch("src.application.news.repositories") as mock_repos,
        patch("src.application.news.news_agent") as mock_agent,
    ):
        news_repo = AsyncMock()
        news_repo.recent_titles.return_value = []
        news_repo.today_news_items.return_value = []
        mock_repos.News.return_value = news_repo

        user = MagicMock()
        user.configuration.news_filter_prompt = ""
        user.configuration.news_preference_profile = ""
        user_repo = AsyncMock()
        user_repo.user_by_id.return_value = user
        mock_repos.User.return_value = user_repo

        mock_agent.run = AsyncMock(return_value=MagicMock(output="Done"))

        from src.application.news import ingest_articles

        result = await ingest_articles(
            candidates=[
                _candidate(
                    title="Python 3.14.2 released",
                    description="First desc",
                    url="http://a",
                ),
                _candidate(
                    title="Python 3.14.2 released",
                    description="Second desc",
                    url="http://b",
                ),
            ],
            source_name="test",
            user_id=1,
        )

    assert result is None
    mock_agent.run.assert_awaited_once()

    user_message = mock_agent.run.call_args.args[0]
    assert "## Article 1" in user_message
    assert "## Article 2" not in user_message
    assert "http://a" in user_message
    assert "http://b" in user_message
    assert "URLs:" in user_message


async def test_ingest_filters_deleted_titles():
    """Candidates matching deleted titles are filtered out
    before reaching the agent."""

    profile = json.dumps(
        {
            "skip": [],
            "high_priority": [],
            "recently_deleted": [
                {"title": "Python 3.14.0a1 Released", "feedback": ""},
            ],
        }
    )

    with (
        patch("src.application.news.repositories") as mock_repos,
        patch("src.application.news.news_agent") as mock_agent,
    ):
        news_repo = AsyncMock()
        news_repo.recent_titles.return_value = []
        news_repo.today_news_items.return_value = []
        mock_repos.News.return_value = news_repo

        user = MagicMock()
        user.configuration.news_filter_prompt = ""
        user.configuration.news_preference_profile = profile
        user_repo = AsyncMock()
        user_repo.user_by_id.return_value = user
        mock_repos.User.return_value = user_repo

        mock_agent.run = AsyncMock(return_value=MagicMock(output="Done"))

        from src.application.news import ingest_articles

        result = await ingest_articles(
            candidates=[
                _candidate(
                    title="Python 3.14.0a1 Released",
                    description="Alpha release",
                    url="http://a",
                ),
                _candidate(
                    title="New AI Framework Launched",
                    description="A new framework",
                    url="http://b",
                ),
            ],
            source_name="test",
            user_id=1,
        )

    assert result is None
    mock_agent.run.assert_awaited_once()
    # Only the non-deleted article should reach the agent
    user_message = mock_agent.run.call_args.args[0]
    assert "New AI Framework" in user_message
    assert "Python 3.14.0a1" not in user_message


async def test_ingest_all_deleted_skips_agent():
    """All candidates match deleted titles → no agent call."""

    profile = json.dumps(
        {
            "skip": [],
            "high_priority": [],
            "recently_deleted": [
                {"title": "Old Article", "feedback": "not relevant"},
            ],
        }
    )

    with (
        patch("src.application.news.repositories") as mock_repos,
        patch("src.application.news.news_agent") as mock_agent,
    ):
        news_repo = AsyncMock()
        news_repo.recent_titles.return_value = []
        mock_repos.News.return_value = news_repo

        user = MagicMock()
        user.configuration.news_filter_prompt = ""
        user.configuration.news_preference_profile = profile
        user_repo = AsyncMock()
        user_repo.user_by_id.return_value = user
        mock_repos.User.return_value = user_repo

        from src.application.news import ingest_articles

        result = await ingest_articles(
            candidates=[_candidate(title="Old Article")],
            source_name="test",
            user_id=1,
        )

    assert result is None
    mock_agent.run.assert_not_called()


async def test_ingest_articles_agent_error_returns_message():
    """Agent failure → returns error string."""

    with (
        patch("src.application.news.repositories") as mock_repos,
        patch("src.application.news.news_agent") as mock_agent,
    ):
        news_repo = AsyncMock()
        news_repo.recent_titles.return_value = []
        news_repo.today_news_items.return_value = []
        mock_repos.News.return_value = news_repo
        user = MagicMock()
        user.configuration.news_filter_prompt = ""
        user.configuration.news_preference_profile = ""
        user_repo = AsyncMock()
        user_repo.user_by_id.return_value = user
        mock_repos.User.return_value = user_repo

        mock_agent.run = AsyncMock(side_effect=RuntimeError("LLM down"))

        from src.application.news import ingest_articles

        result = await ingest_articles(
            candidates=[_candidate()],
            source_name="test",
            user_id=1,
        )

    assert result is not None
    assert "LLM down" in result
