"""News ingestion agent.

Single orchestrating agent that receives an entire feed batch and
decides what to do with each article: filter, merge, or save.
Sub-agent calls are replaced by the orchestrator's own reasoning;
tools handle DB writes and web fetches.
"""

from dataclasses import dataclass, field
from time import perf_counter

import httpx
from loguru import logger
from pydantic_ai import Agent, RunContext, Tool

from src import domain
from src.domain.news import PreferenceRules
from src.infrastructure import database, repositories
from src.infrastructure.agents import AGENT_MODELS, get_model
from src.infrastructure.tracing import get_tracer

# ── Context ──


@dataclass
class NewsIngestionContext:
    source_name: str
    filter_prompt: str
    preference_profile: str
    existing_articles: list[dict] = field(
        default_factory=list
    )  # [{id, title, article_urls}]


# ── Standalone tools ──


async def web_search(url: str) -> str:
    """Fetch a web page for additional context about an article."""

    logger.info(f"AI Web Search: {url}")

    try:
        async with httpx.AsyncClient(
            timeout=15, follow_redirects=True
        ) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                raise Exception(f"Invalid Status Code: {resp.status_code}")
    except Exception as error:
        logger.error(error)
        return "Web search unavailable."
    else:
        return f"Content from {url}:\n{resp.text[:3000]}"


# ── Agent ──

news_agent = Agent(
    get_model(AGENT_MODELS["orchestrator"]),
    deps_type=NewsIngestionContext,
    output_type=str,
    tools=[Tool(web_search, takes_ctx=False)],
)


@news_agent.system_prompt
async def _system_prompt(ctx: RunContext[NewsIngestionContext]) -> str:
    existing = (
        "\n".join(
            f"- ID={a['id']}: \"{a['title']}\""
            for a in ctx.deps.existing_articles
        )
        or "None yet."
    )

    rules = PreferenceRules.from_stored(ctx.deps.preference_profile)
    skip_rules = "\n".join(f"- {s}" for s in rules.skip) or "None yet."
    high_priority_rules = (
        "\n".join(f"- {b}" for b in rules.high_priority) or "None yet."
    )

    if rules.recently_deleted:
        deleted_lines = []
        for d in rules.recently_deleted:
            line = f"- \"{d['title']}\""
            if d.get("feedback"):
                line += f" — user said: \"{d['feedback']}\""
            deleted_lines.append(line)
        deleted_examples = "\n".join(deleted_lines)
    else:
        deleted_examples = "None."

    filter_prompt = ctx.deps.filter_prompt or "No specific filter."

    prompt = domain.prompts.SYSTEM_ORCHESTRATOR.format(
        filter_prompt=filter_prompt,
        high_priority_rules=high_priority_rules,
        skip_rules=skip_rules,
        existing=existing,
        deleted_examples=deleted_examples,
    )

    return prompt


# ── Tools ──


@news_agent.tool
async def save_article(
    ctx: RunContext[NewsIngestionContext],
    title: str,
    description: str,
    urls: str,
) -> str:
    """Save a new article to the database.

    Args:
        title: Article title.
        description: Enriched description.
        urls: Comma-separated article URL(s).
    """

    tracer = get_tracer()
    t0 = perf_counter()

    url_list = [u.strip() for u in urls.split(",") if u.strip()]

    repo = repositories.News()
    item = database.NewsItem(
        title=title,
        description=description,
        sources=[ctx.deps.source_name],
        article_urls=url_list,
    )
    await repo.add_news_item(item)
    await repo.flush()

    # Update merge context for subsequent decisions
    ctx.deps.existing_articles.append(
        {
            "id": item.id,
            "title": title,
            "article_urls": url_list,
        }
    )

    if tracer:
        tracer.record("save", perf_counter() - t0)

    logger.debug(f"Saved: '{title[:60]}' (id={item.id})")
    return f"Saved (id={item.id})"


@news_agent.tool
async def merge_articles(
    ctx: RunContext[NewsIngestionContext],
    existing_id: int,
    description: str,
    urls: str,
) -> str:
    """Merge articles into an existing article that shares the same
    topic signal. Updates both the description and URLs.

    Use this to group articles covering the same theme into one entry.
    Write a new combined description that incorporates the key facts
    from both the existing article and the new articles being merged.

    Args:
        existing_id: ID of the target article to merge into.
        description: Updated description combining existing and new content.
        urls: Comma-separated URL(s) to append.
    """

    tracer = get_tracer()
    t0 = perf_counter()

    url_list = [u.strip() for u in urls.split(",") if u.strip()]

    repo = repositories.News()
    await repo.merge_articles(existing_id, description, url_list)
    await repo.flush()

    if tracer:
        tracer.record("merge", perf_counter() - t0)

    logger.info(f"Merged {len(url_list)} URL(s) into article {existing_id}")

    return f"Merged {len(url_list)} URL(s) into article {existing_id}"


# ── Manual add agent ──


@dataclass
class ManualAddContext:
    url: str


manual_add_agent = Agent(
    get_model(AGENT_MODELS["manual_add"]),
    deps_type=ManualAddContext,
    output_type=str,
    tools=[Tool(web_search, takes_ctx=False)],
)


@manual_add_agent.system_prompt
async def _manual_add_prompt(ctx: RunContext[ManualAddContext]) -> str:
    return domain.prompts.SYSTEM_MANUAL_ADD


@manual_add_agent.tool
async def save_manual_article(
    ctx: RunContext[ManualAddContext], title: str, description: str, urls: str
) -> str:
    """Save the analyzed article to the database.

    Args:
        title: Article title.
        description: Rich analysis of the article content.
        urls: Comma-separated URL(s) — original + references.
    """

    tracer = get_tracer()
    t0 = perf_counter()

    url_list = [u.strip() for u in urls.split(",") if u.strip()]

    repo = repositories.News()
    item = database.NewsItem(
        title=title,
        description=description,
        sources=["manual"],
        article_urls=url_list,
    )
    await repo.add_news_item(item)
    await repo.flush()

    if tracer:
        tracer.record("save", perf_counter() - t0)

    logger.debug(f"Manual save: '{title[:60]}' (id={item.id})")
    return f"Saved (id={item.id})"
