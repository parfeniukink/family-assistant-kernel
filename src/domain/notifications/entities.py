from pydantic import Field

from src.domain.entities import InternalData


class Notification(InternalData):
    """represents a single user notification in the storage.

    ARGS
    ``message`` - the notification message
    ``level`` - defines the value of the level or the emoji that will be
                use in a toaster on user notification
    """

    message: str
    level: str


class Notifications(InternalData):
    """encapsulates all types of notifications that are stored to the cache"""

    big_costs: list[Notification] = Field(default_factory=list)
    incomes: list[Notification] = Field(default_factory=list)
