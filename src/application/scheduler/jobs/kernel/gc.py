from datetime import date, timedelta

from loguru import logger

from src.domain.jobs.registry import register_job_type
from src.infrastructure import repositories
from src.infrastructure.cache import Cache


@register_job_type("kernel", name="Garbage Collector", interval_minutes=240)
async def garbage_collect() -> None:
    """Cleans up old news articles automatically. Removes articles
    with no reactions or bookmarks older than the retention period.
    Bookmarked and reacted articles are kept.

    NOTES
    (1) Runs every 4 hours
    (2) Caches titles of removed items for preference learning
    """

    users = await repositories.User().all_users()

    if not users:
        logger.info("GC: no users found — skipping")
        return

    min_retention = min(u.configuration.gc_retention_days for u in users)

    cutoff = date.today() - timedelta(days=min_retention)
    repo = repositories.News()

    # Cache titles before deletion for preference learning
    titles = await repo.stale_item_titles(before_date=cutoff, limit=20)
    if titles:
        try:
            async with Cache() as cache:
                existing: list = []
                try:
                    existing = await cache.get("gc_deleted_news", "global")
                except Exception:
                    pass

                merged = (existing + titles)[-20:]
                await cache.set(
                    "gc_deleted_news",
                    "global",
                    merged,
                    exptime=259200,  # 3 days
                )
        except Exception as e:
            logger.warning(f"GC: failed to cache deleted titles: {e}")

    count = await repo.delete_stale_items(before_date=cutoff)
    await repo.flush()

    logger.success(
        f"GC: removed {count} items older than {cutoff} "
        f"(retention={min_retention}d)"
    )
