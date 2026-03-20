import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from src.infrastructure import healthcheck, repositories

from . import _primitives as primitives
from ._scheduler import jobs_scheduler


@asynccontextmanager
async def lifespan_event(_: FastAPI):
    """the startup and shutdown application event

    FLOW
    (1) Check Infrastructure connections
    (2) Schedule jobs (trampolines) from Job Entities in DB
    (3) Schedule Worker to process the queue
    """

    await asyncio.gather(
        healthcheck.database_connection(),
        healthcheck.cache_connection(),
    )

    await jobs_scheduler.bootstrap()

    # Seed the seen-URL cache with recent DB article URLs
    news_repo = repositories.News()
    db_urls = await news_repo.existing_article_urls(limit=500)
    await news_repo.cache_seen_urls(list(db_urls))

    worker_task = asyncio.create_task(primitives.worker())
    logger.success("Task scheduler started")

    yield

    primitives.shutdown()
    worker_task.cancel()

    try:
        await worker_task
    except asyncio.CancelledError:
        logger.info("Task scheduler stopped")
