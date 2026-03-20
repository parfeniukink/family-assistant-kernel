import asyncio

import feedparser  # type: ignore[import-untyped]
import httpx
from loguru import logger
from pydantic import BaseModel

from src.application.news import ingest_articles
from src.domain.jobs.registry import register_job_type
from src.domain.jobs.value_objects import JobContext
from src.domain.news.value_objects import ArticleCandidate
from src.infrastructure.tracing import pipeline_tracer


class RssParams(BaseModel):
    url: str


async def _parse_feed(params: RssParams) -> list[ArticleCandidate]:
    """Fetch and parse RSS feed."""

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(params.url)
        response.raise_for_status()

    feed = await asyncio.to_thread(feedparser.parse, response.text)

    candidates: list[ArticleCandidate] = []
    for entry in feed.entries:
        title = entry.get("title", "")
        description = entry.get("summary", "") or entry.get("description", "")
        link = entry.get("link", "")

        if not title or not link:
            continue

        candidates.append(
            ArticleCandidate(
                title=title[:500],
                description=description[:5000],
                url=link[:2048],
            )
        )
    return candidates


@register_job_type(label="rss")
async def fetch_rss(params: RssParams, context: JobContext) -> None:
    """Fetches articles from an RSS feed URL on a schedule.
    New articles are filtered by your preferences and
    deduplicated before saving. Duplicate articles from
    different sources are merged."""

    async with pipeline_tracer(
        f"rss:{context.job_name}", user_id=context.user_id
    ):
        candidates = await _parse_feed(params)
        if not candidates:
            logger.info(f"RSS '{context.job_name}': no entries")
            return
        error = await ingest_articles(
            candidates,
            context.job_name,
            context.user_id,
        )
        if error:
            raise RuntimeError(error)
