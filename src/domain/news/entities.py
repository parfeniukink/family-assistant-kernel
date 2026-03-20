import json
from datetime import datetime

from src.domain.entities import InternalData


class NewsItem(InternalData):
    id: int
    title: str
    description: str
    sources: list[str]
    article_urls: list[str]
    created_at: datetime


class PreferenceRules(InternalData):
    """Structured preference rules learned from user reactions."""

    skip: list[str] = []
    high_priority: list[str] = []
    recently_deleted: list[dict] = []  # [{title, feedback, deleted_at}]

    def to_json(self) -> str:
        return json.dumps(
            {
                "skip": self.skip,
                "high_priority": self.high_priority,
                "recently_deleted": self.recently_deleted,
            }
        )

    @classmethod
    def from_stored(cls, raw: str | None) -> "PreferenceRules":
        """Parse stored profile. Returns empty rules if
        the value is None or old-format prose.

        Backward compatible: reads legacy 'boost' and 'deleted'
        keys if the new keys are absent.
        """

        if not raw:
            return cls()
        try:
            data = json.loads(raw)
            return cls(
                skip=data.get("skip", []),
                high_priority=data.get("high_priority", data.get("boost", [])),
                recently_deleted=data.get(
                    "recently_deleted", data.get("deleted", [])
                ),
            )
        except (json.JSONDecodeError, TypeError):
            return cls()
