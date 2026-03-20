from abc import ABC, abstractmethod

import httpx
from loguru import logger

from src.application.news import ingest_articles
from src.domain.jobs.value_objects import JobContext
from src.domain.news.value_objects import ArticleCandidate
from src.infrastructure.tracing import pipeline_tracer


class WebCrawlerBase(ABC):
    source_name: str
    url: str

    @abstractmethod
    def parse(self, html: str) -> list[ArticleCandidate]:
        """Extract candidates from the page HTML."""

    @abstractmethod
    def parse_article(self, html: str) -> str:
        """Extract full article text from an article page."""

    async def fetch_html(self) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self.url)
            resp.raise_for_status()
            return resp.text

    @staticmethod
    def make_candidate(
        title: str, url: str, description: str = ""
    ) -> ArticleCandidate:
        return ArticleCandidate(
            title=title[:500],
            description=description[:5000],
            url=url[:2048],
        )

    async def enrich_candidates(
        self, candidates: list[ArticleCandidate]
    ) -> list[ArticleCandidate]:
        """Fetch each candidate's URL and replace description
        with full article text."""

        async with httpx.AsyncClient(timeout=30) as client:
            for candidate in candidates:
                try:
                    resp = await client.get(candidate.url)
                    resp.raise_for_status()
                    body = self.parse_article(resp.text)
                    if body:
                        candidate.description = body[:5000]
                except Exception as e:
                    logger.warning(
                        f"Web '{self.source_name}': "
                        f"failed to fetch article "
                        f"{candidate.url}: {e}"
                    )
        return candidates

    async def execute(self, context: JobContext) -> None:
        """Common handler: fetch -> parse -> enrich -> ingest."""

        async with pipeline_tracer(
            f"web:{self.source_name}",
            user_id=context.user_id,
        ):
            html = await self.fetch_html()
            candidates = self.parse(html)
            if not candidates:
                logger.info(
                    f"Web '{self.source_name}': "
                    f"no articles from {self.url}"
                )
                return
            candidates = await self.enrich_candidates(candidates)
            error = await ingest_articles(
                candidates,
                self.source_name,
                context.user_id,
            )
            if error:
                raise RuntimeError(error)
