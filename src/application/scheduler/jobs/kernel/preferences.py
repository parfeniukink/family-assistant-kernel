from datetime import date, timedelta
from time import perf_counter

from loguru import logger

from src.application.agents.preference import (
    PreferenceContext,
    preference_agent,
)
from src.domain.jobs.registry import register_job_type
from src.domain.news import PreferenceRules
from src.domain.news.signals import SIGNAL_WEIGHTS
from src.infrastructure import repositories
from src.infrastructure.cache import Cache
from src.infrastructure.errors import NotFoundError
from src.infrastructure.tracing import pipeline_tracer


async def _load_deleted_signals(user_id: int) -> list[dict]:
    """Read and clear cached deleted-article signals."""

    today = date.today().isoformat()

    try:
        async with Cache() as cache:
            deleted = await cache.get("deleted_news", str(user_id))
            signals = [
                {
                    "title": d["title"],
                    "reaction": None,
                    "bookmarked": False,
                    "feedback": d.get("human_feedback"),
                    "deleted": True,
                    "deleted_at": today,
                    "weight": SIGNAL_WEIGHTS["deleted"],
                }
                for d in deleted
            ]
            await cache.delete("deleted_news", str(user_id))
    except NotFoundError:
        return []
    except Exception as e:
        logger.warning(f"Failed to read deleted articles cache: {e}")
        return []

    return signals


async def _load_gc_deleted_signals() -> list[dict]:
    """Read and clear cached GC-deleted article titles."""

    try:
        async with Cache() as cache:
            titles = await cache.get("gc_deleted_news", "global")
            signals = [
                {
                    "title": t,
                    "reaction": None,
                    "bookmarked": False,
                    "feedback": None,
                    "deleted": True,
                    "gc_deleted": True,
                    "weight": SIGNAL_WEIGHTS["gc_deleted"],
                }
                for t in titles
            ]
            await cache.delete("gc_deleted_news", "global")
    except NotFoundError:
        return []
    except Exception as e:
        logger.warning(f"Failed to read GC deleted cache: {e}")
        return []

    return signals


@register_job_type("kernel", name="Preference Learner", interval_minutes=4320)
async def learn_preferences() -> None:  # noqa: C901
    """Analyzes user reactions to build preference rules.
    Considers reactions, bookmarks, feedback, and article
    removals to build a structured filter for validating
    incoming information.

    NOTES
    (1) Runs every 3 days
    """

    users = await repositories.User().all_users()

    for user in users:
        try:
            await _learn_for_user(user)
        except Exception as e:
            logger.warning(
                f"Preference learning failed for " f"user {user.id}: {e}"
            )


LOOKBACK_DAYS = 14


async def _learn_for_user(user) -> None:  # noqa: C901
    """Run preference learning for a single user."""

    if not user.configuration.analyze_preferences:
        logger.info(f"Preference: user {user.id} has analysis disabled")
        return

    news_repo = repositories.News()
    since = date.today() - timedelta(days=LOOKBACK_DAYS)
    items = await news_repo.recent_reactions(since=since)

    if not items:
        logger.info(f"Preference: user {user.id} has no reactions")
        return

    # Build weighted reaction context
    reactions: list[dict] = []
    for item in items:
        weight = 0
        if item.reaction:
            weight += SIGNAL_WEIGHTS.get(item.reaction, 0)
        if item.bookmarked:
            weight += SIGNAL_WEIGHTS["bookmark"]
        if item.human_feedback:
            weight += SIGNAL_WEIGHTS["human_feedback"]

        reactions.append(
            {
                "title": item.title,
                "reaction": item.reaction,
                "bookmarked": item.bookmarked,
                "feedback": item.human_feedback,
                "weight": weight,
            }
        )

    # Include deleted articles as strong negative signals
    deleted_signals = await _load_deleted_signals(user.id)
    reactions.extend(deleted_signals)

    # Include GC-deleted articles as weak negative signals
    gc_signals = await _load_gc_deleted_signals()
    reactions.extend(gc_signals)

    # Sort by absolute weight (most opinionated first)
    reactions.sort(key=lambda r: abs(r["weight"]), reverse=True)

    n_reacted = len(items)
    n_deleted = len(deleted_signals)
    n_gc = len(gc_signals)
    logger.info(
        f"Preference: user {user.id}: analyzing "
        f"{len(reactions)} articles "
        f"({n_reacted} reacted, {n_deleted} deleted, {n_gc} gc)"
    )

    # Load existing rules for reconciliation
    existing_rules = PreferenceRules()
    filter_prompt = ""
    try:
        profile = user.configuration.news_preference_profile
        existing_rules = PreferenceRules.from_stored(profile)
        filter_prompt = user.configuration.news_filter_prompt or ""
    except Exception as e:
        logger.warning(f"Could not load existing rules: {e}")

    # Merge new deletions with existing recently_deleted
    new_deleted = [
        {
            "title": r["title"],
            "feedback": r.get("feedback"),
            "deleted_at": r.get("deleted_at"),
        }
        for r in deleted_signals
    ]
    merged_deleted = existing_rules.recently_deleted + new_deleted

    # Run preference agent
    ctx = PreferenceContext(
        reactions=reactions,
        filter_prompt=filter_prompt,
        existing_skip=existing_rules.skip,
        existing_high_priority=existing_rules.high_priority,
        existing_recently_deleted=merged_deleted,
    )

    async with pipeline_tracer(
        f"preference:user-{user.id}",
        user_id=user.id,
    ) as tracer:
        t0 = perf_counter()
        result = await preference_agent.run(
            "Analyze these reactions and produce "
            "updated skip/high_priority rules and "
            "recently_deleted list.",
            deps=ctx,
        )
        elapsed = perf_counter() - t0
        tracer.record("preference", elapsed)

        # Store structured rules as JSON
        user_repo = repositories.User()
        await user_repo.update_user(
            user.id,
            news_preference_profile=(result.output.to_json()),
        )
        await user_repo.flush()

        # Clear analysis flag on processed items
        analyzed_ids = [item.id for item in items]
        await news_repo.clear_ai_analysis_flag(analyzed_ids)
        await news_repo.flush()
