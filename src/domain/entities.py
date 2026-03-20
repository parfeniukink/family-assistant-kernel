from pydantic import BaseModel, ConfigDict


class InternalData(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        use_enum_values=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
        from_attributes=True,
    )
