from time import perf_counter
from typing import Literal

from loguru import logger

from src.application.agents.news import (
    ManualAddContext,
    NewsIngestionContext,
    manual_add_agent,
    news_agent,
)
from src.application.agents.perception import (
    AnalysisContext,
    microscope_agent,
    telescope_agent,
)
from src.application.scheduler import submit
from src.domain.news import PreferenceRules
from src.domain.news.value_objects import ArticleCandidate
from src.infrastructure import repositories
from src.infrastructure.tracing import get_tracer, pipeline_tracer

_MAX_BATCH_SIZE = 100

# NOTE: Maps the UI analysis mode to the database column
# that stores the result.
_MODE_TO_COLUMN: dict[str, str] = {
    "microscope": "detailed_description",
    "telescope": "extended_description",
}


def _normalize(title: str) -> str:
    return " ".join(title.casefold().split())[:20]


async def extend_article(
    item_id: int,
    mode: Literal["microscope", "telescope"],
    user_id: int,
) -> None:
    """Submit an inference task to extend a news item.

    NOTES
    (1) Works in 2 modes:
        - 🔬: specialized context (dig into that field specifically)
        - 🔭: broad context (where topic could be included into)
    """

    news_repo = repositories.News()
    user_repo = repositories.User()

    try:
        item = await news_repo.get_news_item(id_=item_id)
        feedback_history = await news_repo.recent_feedback(limit=50)
    except Exception as e:
        logger.error(f"extend_article: failed to load item {item_id}: {e}")
        return

    # Load user preference profile
    user = await user_repo.user_by_id(user_id)
    preference_profile = user.configuration.news_preference_profile or ""

    user_message = f"## {item.title}\n\n{item.description}"
    column = _MODE_TO_COLUMN[mode]
    agent = microscope_agent if mode == "microscope" else telescope_agent

    context = AnalysisContext(
        title=item.title,
        description=item.description,
        feedback_history=feedback_history,
        preference_profile=preference_profile,
    )

    async def _handler() -> None:
        async with pipeline_tracer(
            f"extend:{mode}:{item_id}", user_id=user_id
        ) as tracer:
            t0 = perf_counter()
            result = await agent.run(user_message, deps=context)
            elapsed = perf_counter() - t0
            tracer.record(mode, elapsed)

            repo = repositories.News()
            await repo.set_description_field(
                id_=item_id, column=column, text=result.output
            )
            await repo.flush()

    submit(name=f"extend:{mode}:{item_id}", handler=_handler)


async def add_manual_article(url: str, user_id: int) -> None:
    """Submit a manually added article for AI analysis."""

    repo = repositories.News()
    if await repo.url_exists(url):
        raise ValueError("Article already exists")

    context = ManualAddContext(url=url)

    async def _handler() -> None:
        async with pipeline_tracer("manual_add", user_id=user_id) as tracer:
            t0 = perf_counter()
            await manual_add_agent.run(
                f"Analyze this article: {url}",
                deps=context,
            )
            tracer.record("manual_add", perf_counter() - t0)

    submit(
        name=f"manual_add:{url[:60]}",
        handler=_handler,
    )


async def ingest_articles(  # noqa: C901
    candidates: list[ArticleCandidate], source_name: str, user_id: int
) -> str | None:
    """Dedup candidates, then let the news agent process the
    batch. Returns None on success, error string on failure.

    NOTE: This function is used by each scheduler that is related
          to the News aggregation.

    """

    # (1) Skip candidates whose URL was already seen (cache)
    news_repo = repositories.News()
    tracer = get_tracer()
    seen_urls = await news_repo.cached_seen_urls()

    candidates_without_duplicates = [
        c for c in candidates if c.url not in seen_urls
    ]

    if tracer:
        tracer.set_meta("candidates", len(candidates))
        tracer.set_meta(
            "cache_dedup",
            -(len(candidates) - len(candidates_without_duplicates)),
        )

    if not candidates_without_duplicates:
        logger.info(f"'{source_name}': all entries already exist")
        return None

    # 2. Load user preferences (needed for deleted-title filter)
    user = await repositories.User().user_by_id(user_id)
    filter_prompt = user.configuration.news_filter_prompt or ""
    preference_profile = user.configuration.news_preference_profile or ""

    # 3. Filter out previously deleted articles
    rules = PreferenceRules.from_stored(preference_profile)
    deleted_norm = {_normalize(d["title"]) for d in rules.recently_deleted}
    before = len(candidates_without_duplicates)
    candidates_without_duplicates = [
        c
        for c in candidates_without_duplicates
        if _normalize(c.title) not in deleted_norm
    ]
    if before != len(candidates_without_duplicates):
        logger.info(
            f"'{source_name}': filtered "
            f"{before - len(candidates_without_duplicates)} "
            f"previously deleted articles"
        )

    if tracer:
        tracer.set_meta(
            "deleted_filter",
            -(before - len(candidates_without_duplicates)),
        )

    if not candidates_without_duplicates:
        logger.info(f"'{source_name}': all entries filtered")
        return None

    # 4. Within-batch title dedup (collapse same-title entries)
    before_dedup = len(candidates_without_duplicates)
    seen: dict[str, ArticleCandidate] = {}
    for c in candidates_without_duplicates:
        key = _normalize(c.title)
        if key in seen:
            seen[key].extra_urls.append(c.url)
        else:
            seen[key] = c
    candidates_without_duplicates = list(seen.values())

    if tracer:
        tracer.set_meta(
            "batch_dedup",
            -(before_dedup - len(candidates_without_duplicates)),
        )
        tracer.set_meta("\u2192 to_agent", len(candidates_without_duplicates))

    logger.info(
        f"'{source_name}': "
        f"processing {len(candidates_without_duplicates)} articles"
    )

    # 5–7. Process in batches of _MAX_BATCH_SIZE
    try:
        total = len(candidates_without_duplicates)
        for batch_idx in range(0, total, _MAX_BATCH_SIZE):
            end = batch_idx + _MAX_BATCH_SIZE
            batch = candidates_without_duplicates[batch_idx:end]
            batch_num = batch_idx // _MAX_BATCH_SIZE + 1

            # Reload today's articles each batch (prior batch may
            # have added new ones)
            today_items = await news_repo.today_news_items()
            existing_articles = [
                {
                    "id": item.id,
                    "title": item.title,
                    "article_urls": item.article_urls or [],
                }
                for item in today_items
            ]

            # Format only this batch
            parts: list[str] = []
            for i, c in enumerate(batch, 1):
                urls = c.all_urls
                if len(urls) == 1:
                    url_line = f"URL: {urls[0]}"
                else:
                    url_line = "URLs: " + ", ".join(urls)
                parts.append(
                    f"## Article {i}\n"
                    f"Title: {c.title}\n"
                    f"Description: {c.description}\n"
                    f"{url_line}"
                )
            user_message = (
                f"Process these candidate articles from "
                f'"{source_name}":\n\n' + "\n\n".join(parts)
            )

            context = NewsIngestionContext(
                source_name=source_name,
                filter_prompt=filter_prompt,
                preference_profile=preference_profile,
                existing_articles=existing_articles,
            )

            t0 = perf_counter()
            try:
                await news_agent.run(user_message, deps=context)
            except Exception as e:
                if tracer:
                    tracer.record(
                        "orchestrator",
                        perf_counter() - t0,
                        error=True,
                    )
                logger.error(
                    f"News agent error for '{source_name}' "
                    f"(batch {batch_num}): {e}"
                )
                return str(e)[:1000]

            if tracer:
                tracer.record("orchestrator", perf_counter() - t0)
    finally:
        # Cache all candidate URLs as "seen" (saved or filtered)
        all_urls = [c.url for c in candidates]
        await news_repo.cache_seen_urls(all_urls)

    return None
