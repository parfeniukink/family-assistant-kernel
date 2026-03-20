from contextlib import suppress
from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, Query, status
from loguru import logger

from src import application as op
from src import domain
from src.application.news import add_manual_article, extend_article
from src.infrastructure import (
    OffsetPagination,
    ResponseMultiPaginated,
    database,
    get_offset_pagination_params,
    repositories,
)
from src.infrastructure.cache import Cache
from src.infrastructure.errors import NotFoundError

from ..contracts.news import (
    REACTION_OPTIONS,
    ManualArticleBody,
    NewsGroup,
    NewsGroupItem,
    NewsGroupsResponse,
    NewsItem,
    NewsItemDetail,
    NewsItemFeedbackBody,
    NewsItemReactBody,
    NewsSourceBlock,
)

router = APIRouter(prefix="/news", tags=["News"])


@router.get("", status_code=status.HTTP_200_OK)
async def news_items(
    _=Depends(op.authorize),
    pagination: OffsetPagination = Depends(get_offset_pagination_params),
) -> ResponseMultiPaginated[NewsItem]:
    """Paginated news items."""

    repo = repositories.News()
    items, total = await repo.news_items(
        offset=pagination.context, limit=pagination.limit
    )

    if items:
        context: int = pagination.context + len(items)
        left: int = total - context
    else:
        context = 0
        left = 0

    return ResponseMultiPaginated[NewsItem](
        result=[NewsItem.from_instance(item) for item in items],
        context=context,
        left=left,
    )


@router.get("/groups", status_code=status.HTTP_200_OK)
async def news_groups(
    _=Depends(op.authorize),
    start_date: Annotated[
        date | None,
        Query(
            description="Start of the date window",
            alias="startDate",
        ),
    ] = None,
    end_date: Annotated[
        date | None,
        Query(
            description="End of the date window",
            alias="endDate",
        ),
    ] = None,
    bookmarked: Annotated[
        bool | None,
        Query(
            description="Filter by bookmarked status",
            alias="bookmarked",
        ),
    ] = None,
    reaction: Annotated[
        str | None,
        Query(
            description="Filter by reaction emoji",
            alias="reaction",
        ),
    ] = None,
    commented: Annotated[
        bool | None,
        Query(
            description="Filter by has human feedback",
            alias="commented",
        ),
    ] = None,
) -> NewsGroupsResponse:
    """News items aggregated by day within a date range."""

    # When filtering by bookmarks or comments, show all dates
    if not bookmarked and not commented:
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=6)

    repo = repositories.News()

    grouped = await repo.news_items_for_date_range(
        start_date,
        end_date,
        bookmarked=bookmarked,
        reaction=reaction,
        commented=commented,
    )
    earliest = await repo.earliest_news_date()

    result: list[NewsGroup] = []
    for day in sorted(grouped.keys(), reverse=True):
        day_items = grouped[day]

        # Group items by their first source
        source_map: dict[str, list[database.NewsItem]] = {}
        for item in day_items:
            source = (item.sources or ["Unknown"])[0]
            source_map.setdefault(source, []).append(item)

        blocks = [
            NewsSourceBlock(
                source=source,
                items=[NewsGroupItem.from_instance(i) for i in items],
            )
            for source, items in source_map.items()
        ]

        result.append(NewsGroup(date=day, blocks=blocks))

    return NewsGroupsResponse(
        result=result,
        earliest_date=earliest,
    )


@router.get("/reactions", status_code=status.HTTP_200_OK)
async def news_reaction_options(
    _=Depends(op.authorize),
) -> list[str]:
    """Available reaction emoji options."""

    return REACTION_OPTIONS


@router.post("/manual", status_code=status.HTTP_202_ACCEPTED)
async def news_manual_add(
    body: ManualArticleBody = Body(...),
    user: domain.users.User = Depends(op.authorize),
) -> None:
    """Submit a URL for AI-powered article analysis."""

    await add_manual_article(body.url, user_id=user.id)


@router.get("/{item_id}", status_code=status.HTTP_200_OK)
async def news_item_detail(
    item_id: int,
    _=Depends(op.authorize),
) -> NewsItemDetail:
    """Full detail for a single news item."""

    item = await repositories.News().get_news_item(id_=item_id)
    return NewsItemDetail.from_instance(item)


@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def news_item_delete(
    item_id: int,
    user: domain.users.User = Depends(op.authorize),
) -> None:
    """Delete a news item."""

    repo = repositories.News()
    item = await repo.get_news_item(id_=item_id)

    # Cache dump for preference learning
    dump = {
        "title": item.title,
        "description": item.description,
        "human_feedback": item.human_feedback,
        "sources": item.sources or [],
    }
    try:
        async with Cache() as cache:
            existing: list = []

            # Try to override with existing in the Cache
            with suppress(NotFoundError, ValueError):
                raw = await cache.get("deleted_news", str(user.id))
                if isinstance(raw, list):
                    existing = raw

            existing.append(dump)

            await cache.set(
                "deleted_news",
                str(user.id),
                existing,
                exptime=86400,  # 24 hours
            )
    except Exception as error:
        logger.error("Failed to cache deleted article signal")
        logger.error(error)
    else:
        logger.info(
            "Removed article is added to the cache " "for future analytics"
        )

    await repo.delete_news_item(id_=item_id)
    await repo.flush()


@router.post(
    "/{item_id}/bookmark",
    status_code=status.HTTP_200_OK,
)
async def news_item_bookmark(
    item_id: int,
    _=Depends(op.authorize),
) -> NewsGroupItem:
    """Toggle bookmark on a news item."""

    repo = repositories.News()
    item = await repo.toggle_bookmark(id_=item_id)
    await repo.flush()

    return NewsGroupItem.from_instance(item)


@router.post("/{item_id}/react")
async def news_item_react(
    item_id: int, body: NewsItemReactBody = Body(...), _=Depends(op.authorize)
) -> NewsGroupItem:
    """Set or clear reaction on a news item."""

    repo = repositories.News()
    item = await repo.set_reaction(id_=item_id, reaction=body.reaction)
    await repo.flush()

    return NewsGroupItem.from_instance(item)


@router.patch("/{item_id}/feedback")
async def news_item_feedback(
    item_id: int,
    body: NewsItemFeedbackBody = Body(...),
    _=Depends(op.authorize),
) -> NewsItemDetail:
    """Set or clear human feedback on a news item."""

    repo = repositories.News()
    item = await repo.set_human_feedback(
        id_=item_id, feedback=body.human_feedback
    )
    await repo.flush()

    return NewsItemDetail.from_instance(item)


@router.post("/{item_id}/extend/{mode}", status_code=status.HTTP_202_ACCEPTED)
async def news_item_extend(
    item_id: int,
    mode: Literal["microscope", "telescope"],
    user: domain.users.User = Depends(op.authorize),
) -> None:
    """Trigger AI analysis for a news item (non-blocking)."""

    await extend_article(item_id, mode, user_id=user.id)
