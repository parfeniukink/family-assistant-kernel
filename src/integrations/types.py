from pydantic import BaseModel, ConfigDict, alias_generators


class ExternalData(BaseModel):
    """Base for external API response models."""

    model_config = ConfigDict(
        extra="ignore",
        populate_by_name=True,
        alias_generator=alias_generators.to_camel,
    )
