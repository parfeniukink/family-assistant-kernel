import json

from bs4 import BeautifulSoup
from loguru import logger
from pydantic import BaseModel

from src.application.scheduler.jobs.crawlers._base import WebCrawlerBase
from src.domain.jobs.registry import register_job_type
from src.domain.jobs.value_objects import JobContext
from src.domain.news.value_objects import ArticleCandidate


class IaiTvParams(BaseModel):
    pass


class IaiTvCrawler(WebCrawlerBase):
    source_name = "iai.tv"
    url = "https://iai.tv/articles-proxy"

    def _extract_from_widget(self, widget: dict) -> list[ArticleCandidate]:
        sprops = widget.get("Sprops")
        if not isinstance(sprops, list):
            return []

        candidates: list[ArticleCandidate] = []
        for item in sprops:
            if not isinstance(item, dict):
                continue
            if item.get("_KIND_") != "article":
                continue

            title = item.get("Title", "")
            link = item.get("Link", "")
            if not title or not link:
                continue

            url = link if link.startswith("http") else f"https://iai.tv{link}"
            candidates.append(
                self.make_candidate(
                    title=title,
                    url=url,
                    description=item.get("Subtitle", ""),
                )
            )
        return candidates

    @staticmethod
    def _body_from_widgets(widgets: list) -> str:
        """Find first Body field in widget Sprops."""

        for widget in widgets:
            sprops = widget.get("Sprops")
            if not isinstance(sprops, list):
                continue
            for item in sprops:
                if not isinstance(item, dict):
                    continue
                body_html = item.get("Body", "")
                if body_html:
                    body_soup = BeautifulSoup(body_html, "html.parser")
                    return body_soup.get_text(separator=" ", strip=True)
        return ""

    def _extract_body_from_js_vars(self, soup: BeautifulSoup) -> str:
        """Try to extract article body from JS_VARS JSON."""

        for tag in soup.find_all("script"):
            text = tag.string or ""
            marker = "window.JS_VARS ="
            pos = text.find(marker)
            if pos == -1:
                continue

            try:
                start = text.find("{", pos + len(marker))
                end = text.rfind("}")
                if start == -1 or end == -1:
                    continue
                data = json.loads(text[start : end + 1])  # noqa: E203
                widgets = data.get("Widgets", {}).get("widgets", [])
            except Exception:
                continue

            body = self._body_from_widgets(widgets)

            if body:
                return body

        return ""

    def parse_article(self, html: str) -> str:
        """Extract full article text from an IAI.tv article
        page."""

        soup = BeautifulSoup(html, "html.parser")

        body = self._extract_body_from_js_vars(soup)
        if body:
            return body

        # Fallback: extract from main content container
        for selector in [
            "article",
            ".article-body",
            ".article-content",
            "main",
        ]:
            container = soup.select_one(selector)
            if container:
                return container.get_text(separator=" ", strip=True)

        return ""

    def parse(self, html: str) -> list[ArticleCandidate]:
        soup = BeautifulSoup(html, "html.parser")
        articles: list[ArticleCandidate] = []

        for tag in soup.find_all("script"):
            # (1) Filter only `scripts` section with JS_VARS
            text = tag.string or ""
            marker = "window.JS_VARS ="
            pos = text.find(marker)
            if pos == -1:
                continue

            # (2) Extract JSON from: window.JS_VARS = {...};
            try:
                start = text.find("{", pos + len(marker))
                end = text.rfind("}")
                if start == -1 or end == -1:
                    continue

                data = json.loads(text[start : end + 1])  # noqa: E203
                _widgets = data["Widgets"]["widgets"]
            except Exception as error:
                logger.error(error)
                raise ValueError(
                    "Can not parse the HTML of the " "IAI Web resource"
                ) from error
            else:
                if not isinstance(_widgets, list):
                    raise ValueError(
                        f"Invalid type '{type(_widgets)}'"
                        " for widgets in scripts"
                    )

            # (3) Extract articles from each widget
            for widget in _widgets:
                articles.extend(self._extract_from_widget(widget))

        return articles


_crawler = IaiTvCrawler()


@register_job_type(label="crawler", name="IAI.tv Articles")
async def fetch_iai(params: IaiTvParams, context: JobContext) -> None:
    """Crawls iai.tv for philosophy and ideas articles.
    New articles are filtered by your preferences and
    deduplicated before saving."""

    await _crawler.execute(context)
