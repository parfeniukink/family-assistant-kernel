"""
this file is a part of infrastructure tier of the application.
it is base on pydantic_settings engine to make it easy to work
with environment variables (including ``.env`` file support).

HOW TO WORK WITH SETTIGNS?
1. focus on ``Settings`` class
2. if you would like to change the ``debug`` parameter go to the ``.env``
    file and add ``FBB__DEBUG``, since there is a prefix specified in
    ``model_config`` of that class
3. if you would like to change the nested parameter - use next prfix as well:
    ``FBB__DATABASE__NAME`` respectively
"""

__all__ = ("settings",)

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    driver: str = "postgresql+asyncpg"
    host: str = "database"
    port: int = 5432
    user: str = "postgres"
    password: str = "postgres"
    name: str = "family_budget"

    @property
    def url(self) -> str:
        return (
            f"{self.driver}://"
            f"{self.user}:{self.password}@"
            f"{self.host}:{self.port}/"
            f"{self.name}"
        )

    @property
    def default_database_url(self) -> str:
        """returns the url to the default database."""

        return (
            f"{self.driver}://"
            f"{self.user}:{self.password}@"
            f"{self.host}:{self.port}/"
            f"postgres"
        )


class CacheSettings(BaseModel):
    host: str = "cache"
    port: int = 11211
    pool: int = 2


class CORSSettings(BaseModel):
    allow_origins: list[str] = ["*"]
    allow_methods: list[str] = [
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ]
    allow_headers: list[str] = [
        "Authorization",
        "Content-Type",
    ]
    allow_credentials: bool = True
    expose_headers: list[str] = []
    max_age: int = 600


class LoggingSettings(BaseModel):
    """Configure the logging engine."""

    # The time field can be formatted using more human-friendly tokens.
    # These constitute a subset of the one used by the Pendulum library
    # https://pendulum.eustace.io/docs/#tokens
    format: str = "{time:YYYY-MM-DD HH:mm:ss} | {level: <5} | {message}"
    level: str = "INFO"
    file: str = "/tmp/fambb.log"
    rotation: str = "10MB"
    compression: str = "zip"


class MonobankSettings(BaseModel):
    webhook_secret: str = "webhook"


class AuthSettings(BaseModel):
    secret_key: str = "CHANGE_ME_IN_PRODUCTION"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7


class OpenAISettings(BaseModel):
    api_key: str = ""
    default_model: str = "gpt-4.1-mini"


class RateLimitSettings(BaseModel):
    login_per_minute: int = 5
    login_per_hour: int = 20
    refresh_per_minute: int = 10


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FBB__",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )
    debug: bool = False
    timezone: str = "UTC"
    logging: LoggingSettings = LoggingSettings()
    cors: CORSSettings = CORSSettings()
    database: DatabaseSettings = DatabaseSettings()
    cache: CacheSettings = CacheSettings()

    openai: OpenAISettings = OpenAISettings()
    monobank: MonobankSettings = MonobankSettings()
    auth: AuthSettings = AuthSettings()
    rate_limit: RateLimitSettings = RateLimitSettings()
    pytest_logging: str = "off"

    # INTEGRATIONS
    sentry_dsn: str | None = None


settings = Settings()
