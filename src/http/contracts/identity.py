import functools
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator

from src import domain
from src.infrastructure.responses import PublicData

from .currency import Currency
from .transactions import CostCategory


# ─────────────────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────────────────
class GetTokensRequestBody(PublicData):
    """Login request body."""

    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=255)


class RefreshRequestBody(PublicData):
    """Token refresh request body."""

    refresh_token: str


class TokenPairResponse(PublicData):
    """Token pair response."""

    access_token: str
    refresh_token: str


# ─────────────────────────────────────────────────────────
# USER
# ─────────────────────────────────────────────────────────
class UserConfiguration(PublicData):
    show_equity: bool = Field(
        default=False, description="Define if the equity is visible"
    )
    default_currency: Currency | None = Field(
        default=None, description="A default currency costs and incomes"
    )
    default_cost_category: CostCategory | None = Field(
        default=None, description="A default currency costs and incomes"
    )
    cost_snippets: list[str] | None = Field(
        default=None,
        description="The list of available snippets for the cost name",
    )
    income_snippets: list[str] | None = Field(
        default=None,
        description="The list of available snippets for the income name",
    )
    notify_cost_threshold: float | None = Field(
        default=None,
        description=(
            "The thrashhold for the value, to be notified "
            "about costs. NOT in CENTS"
        ),
    )
    pagination_items: int = Field(
        default=10,
        description="A number of paginated items in transactions analytics",
    )

    monobank_integration_active: bool = Field(
        default=False,
        description=(
            "Monobank API Key is not exposed. "
            "You can only see that it is available to use."
        ),
    )
    news_filter_prompt: str | None = Field(
        default=None,
        description="LLM prompt for filtering news articles",
    )
    news_preference_profile: str | None = Field(
        default=None,
        description="AI-generated user preference profile for news",
    )
    gc_retention_days: int = Field(
        default=3,
        description="Days to retain news articles before GC",
    )
    analyze_preferences: bool = Field(
        default=True,
        description="Whether AI should analyze user preferences",
    )
    timezone: str = Field(
        default="UTC",
        description="IANA timezone for the user",
    )

    @functools.singledispatchmethod
    @classmethod
    def from_instance(cls, instance) -> "UserConfiguration":
        raise NotImplementedError(
            f"Can not get {cls.__name__} from {type(instance)} type"
        )

    @from_instance.register
    @classmethod
    def _(cls, instance: domain.users.UserConfiguration):
        return cls(
            **instance.model_dump(),
            monobank_integration_active=(
                True if instance.monobank_api_key else False
            ),
        )

    @field_validator("notify_cost_threshold", mode="after")
    @classmethod
    def notify_cost_threshold_prettify(
        cls, value: float | None
    ) -> float | None:
        if value is not None:
            return domain.transactions.pretty_money(value)
        else:
            return value


class UserConfigurationPartialUpdateRequestBody(PublicData):
    show_equity: bool = Field(
        default=False, description="Define if the equity is visible"
    )
    default_currency_id: int | None = Field(
        default=None, description="Update the default_currency_id"
    )
    default_cost_category_id: int | None = Field(
        default=None, description="Update the default_cost_category_id"
    )
    cost_snippets: list[str] | None = Field(
        default=None,
        description="A list of available snippets for the cost name",
    )
    income_snippets: list[str] | None = Field(
        default=None,
        description="A list of available snippets for the income name",
    )
    notify_cost_threshold: float | None = Field(
        default=None,
        description="A thrashhold to be notified about others costs",
    )
    pagination_items: int | None = Field(
        default=None,
        description="A number of paginated items in transactions analytics",
    )
    monobank_api_key: str | None = Field(
        default=None,
        description="Monobank API Key. https://api.monobank.ua/index.html",
    )
    news_filter_prompt: str | None = Field(
        default=None,
        description="LLM prompt for filtering news articles",
    )
    news_preference_profile: str | None = Field(
        default=None,
        description="AI-generated user preference profile for news",
    )
    gc_retention_days: int | None = Field(
        default=None,
        description="Days to retain news articles before GC",
    )
    analyze_preferences: bool | None = Field(
        default=None,
        description="Whether AI should analyze user preferences",
    )
    timezone: str | None = Field(
        default=None,
        description="IANA timezone (e.g. 'Europe/Kyiv')",
    )

    @field_validator("timezone", mode="after")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value)
            except (KeyError, ValueError):
                raise ValueError(f"Invalid timezone: {value}")
        return value

    @field_validator("notify_cost_threshold", mode="after")
    @classmethod
    def notify_cost_threshold_to_cents(cls, value: float | None) -> int | None:
        if value is not None:
            return domain.transactions.cents_from_raw(value)
        else:
            return value


class UserCreateRequestBody(PublicData):
    """create a new user HTTP request body schema."""

    name: str


class User(PublicData):
    id: int
    name: str
    configuration: UserConfiguration = UserConfiguration()

    @functools.singledispatchmethod
    @classmethod
    def from_instance(cls, instance) -> "User":
        raise NotImplementedError(
            f"Can not get {cls.__name__} from {type(instance)} type"
        )

    @from_instance.register
    @classmethod
    def _(cls, instance: domain.users.User):
        return cls(
            id=instance.id,
            name=instance.name,
            configuration=UserConfiguration.from_instance(
                instance.configuration
            ),
        )
