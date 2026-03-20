import functools
from datetime import date, datetime

from pydantic import Field

from src.infrastructure import database
from src.infrastructure.responses import PublicData


class NewsItem(PublicData):
    id: int
    title: str
    description: str
    sources: list[str]
    article_urls: list[str]
    created_at: datetime

    @functools.singledispatchmethod
    @classmethod
    def from_instance(cls, instance) -> "NewsItem":
        raise NotImplementedError(
            f"Can not convert {type(instance)} into NewsItem"
        )

    @from_instance.register
    @classmethod
    def _(cls, instance: database.NewsItem):
        return cls(
            id=instance.id,
            title=instance.title,
            description=instance.description,
            sources=instance.sources or [],
            article_urls=instance.article_urls or [],
            created_at=instance.created_at,
        )


class NewsGroupItem(PublicData):
    id: int
    title: str
    article_urls: list[str]
    article_count: int
    viewed: bool
    bookmarked: bool
    reaction: str | None
    has_detailed_description: bool
    has_extended_description: bool
    has_human_feedback: bool

    @functools.singledispatchmethod
    @classmethod
    def from_instance(cls, instance) -> "NewsGroupItem":
        raise NotImplementedError

    @from_instance.register
    @classmethod
    def _(cls, instance: database.NewsItem):
        urls = instance.article_urls or []
        return cls(
            id=instance.id,
            title=instance.title,
            article_urls=urls,
            article_count=len(urls),
            viewed=instance.reaction is not None,
            bookmarked=instance.bookmarked,
            reaction=instance.reaction,
            has_detailed_description=bool(instance.detailed_description),
            has_extended_description=bool(instance.extended_description),
            has_human_feedback=bool(instance.human_feedback),
        )


class NewsItemDetail(PublicData):
    id: int
    title: str
    description: str
    article_urls: list[str]
    article_count: int
    viewed: bool
    bookmarked: bool
    reaction: str | None
    detailed_description: str | None
    extended_description: str | None
    human_feedback: str | None

    @functools.singledispatchmethod
    @classmethod
    def from_instance(cls, instance) -> "NewsItemDetail":
        raise NotImplementedError

    @from_instance.register
    @classmethod
    def _(cls, instance: database.NewsItem):
        urls = instance.article_urls or []
        return cls(
            id=instance.id,
            title=instance.title,
            description=instance.description,
            article_urls=urls,
            article_count=len(urls),
            viewed=instance.reaction is not None,
            bookmarked=instance.bookmarked,
            reaction=instance.reaction,
            detailed_description=instance.detailed_description,
            extended_description=instance.extended_description,
            human_feedback=instance.human_feedback,
        )


class NewsSourceBlock(PublicData):
    source: str
    items: list[NewsGroupItem]


class NewsGroup(PublicData):
    date: date
    blocks: list[NewsSourceBlock]


class NewsGroupsResponse(PublicData):
    result: list[NewsGroup]
    earliest_date: date | None


REACTION_OPTIONS: list[str] = [
    "\U0001f525",  # hot / groundbreaking
    "\U0001f440",  # interesting / watching
    "\U0001f610",  # neutral / meh
    "\U0001f44e",  # bad / misleading
]


class NewsItemReactBody(PublicData):
    reaction: str | None = Field(default=None, max_length=10)


class NewsItemFeedbackBody(PublicData):
    human_feedback: str | None = Field(default=None, max_length=5000)


class ManualArticleBody(PublicData):
    url: str = Field(max_length=2048)
