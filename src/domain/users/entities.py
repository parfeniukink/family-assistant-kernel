from src.domain.entities import InternalData
from src.domain.equity import Currency
from src.domain.transactions import CostCategory


class UserConfiguration(InternalData):
    """User configuration is a part of a ``users`` table."""

    show_equity: bool = False
    default_currency: Currency | None = None
    default_cost_category: CostCategory | None = None
    cost_snippets: list[str] | None = None
    income_snippets: list[str] | None = None

    last_notification: str | None = None
    notify_cost_threshold: int | None = None

    monobank_api_key: str | None = None

    # news preferences
    news_filter_prompt: str | None = None
    news_preference_profile: str | None = None
    gc_retention_days: int = 3
    analyze_preferences: bool = True
    timezone: str = "UTC"


class User(InternalData):
    """Extended user data object with configuration details."""

    id: int
    name: str
    configuration: UserConfiguration
