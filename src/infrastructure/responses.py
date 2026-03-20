import json
from collections.abc import Sequence
from typing import Any, Generic, Literal, TypeVar

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field, alias_generators, conlist

ErrorType = Literal["internal", "external", "missing", "bad-type"]


class PublicData(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        use_enum_values=True,
        validate_assignment=True,
        populate_by_name=True,
        arbitrary_types_allowed=True,
        from_attributes=True,
        loc_by_alias=True,
        alias_generator=alias_generators.to_camel,
    )

    def json_body(self, /, *, exclude_unset=True) -> dict[str, Any]:
        """try to convert to the dictionary with some adjustment."""

        try:
            return json.loads(
                self.model_dump_json(exclude_unset=exclude_unset)
            )
        except json.JSONDecodeError as error:
            raise ValueError(
                f"{self.__class__.__name__} instance in not"
                " JSON serializable"
            ) from error


_TPublicData = TypeVar("_TPublicData", bound=PublicData)


# =====================================================================
# RESPONSES
# =====================================================================
class Response(PublicData, Generic[_TPublicData]):
    """Generic response model that consist only one result."""

    result: _TPublicData


class ResponseMulti(PublicData, Generic[_TPublicData]):
    """Generic response model that consist multiple results."""

    result: Sequence[_TPublicData]


# =====================================================================
# ERROR RESPONSES
# =====================================================================
class ErrorDetail(PublicData):
    """Error detail model."""

    path: tuple[str | int, ...] = Field(
        description="The path to the field that raised the error",
        default_factory=tuple,
    )
    type: ErrorType = Field(description="The error type", default="internal")


class ErrorResponse(PublicData):
    """Error response model."""

    message: str = Field(description="This field represent the message")
    detail: ErrorDetail = Field(
        description="This field represents error details",
        default_factory=ErrorDetail,
    )


class ErrorResponseMulti(PublicData):
    """The public error respnse model that includes multiple objects."""

    result: conlist(ErrorResponse, min_length=1)  # type: ignore


# =====================================================================
# PAGINATION
# =====================================================================
class ResponseMultiPaginated(PublicData, Generic[_TPublicData]):
    """Generic response model that consist multiple results,
    paginated with cursor pagination.
    """

    result: Sequence[_TPublicData]
    context: int = Field(
        description=(
            "the user ID that should be used for the "
            "next request to get proper pagination"
        )
    )
    left: int = Field(description="How many items is left")


class OffsetPagination(PublicData):
    """cursor pagination HTTP query parameters"""

    context: int = Field(description="ID limiting start position")
    limit: int = Field(description="limit total items in results")


def get_offset_pagination_params(
    context: int | None = Query(
        default=None,
        description="The highest id of previously received item list",
    ),
    limit: int | None = Query(
        default=None,
        description="Limit results total items",
    ),
) -> OffsetPagination:
    """FastAPI HTTP GET query params.

    usage:
        ```py
        @router.get("")
        async def controller(
            pagination: OffsetPagination = fastapi.Depends(
                get_offset_pagination_params
            )
        ):
            ...
    """

    return OffsetPagination(context=context or 0, limit=limit or 10)
