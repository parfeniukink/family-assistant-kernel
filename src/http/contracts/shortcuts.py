import contextlib
import functools
from datetime import date

from pydantic import Field

from src import domain
from src.infrastructure import database
from src.infrastructure.responses import PublicData

from ._mixins import _ValueValidationMixin
from .currency import Currency
from .transactions import CostCategory


class CostShortcutCreateBody(PublicData, _ValueValidationMixin):
    """The request body to create a new cost."""

    name: str = Field(description="The name of the cost")
    value: float | None = Field(default=None, examples=[12.2, 650, None])
    currency_id: int
    category_id: int

    @property
    def value_in_cents(self) -> int | None:
        with contextlib.suppress(ValueError):
            return domain.transactions.cents_from_raw(self.value)

        return None


class CostShortcutUI(PublicData):
    """UI preferences for the CostShortcut instance."""

    position_index: int


class CostShortcut(PublicData):
    id: int
    name: str = Field(description="The name of the cost")
    value: float | None = Field(default=None, examples=[12.2, 650, None])
    currency: Currency
    category: CostCategory
    ui: CostShortcutUI

    @functools.singledispatchmethod
    @classmethod
    def from_instance(cls, instance) -> "CostShortcut":
        raise NotImplementedError(
            f"Can not get {cls.__name__} from {type(instance)} type"
        )

    @from_instance.register
    @classmethod
    def _(cls, instance: database.CostShortcut):
        return cls(
            id=instance.id,
            name=instance.name,
            value=(
                domain.transactions.pretty_money(instance.value)
                if instance.value
                else None
            ),
            currency=Currency.model_validate(instance.currency),
            category=CostCategory.model_validate(instance.category),
            ui=CostShortcutUI(
                position_index=instance.ui_position_index or 0,
            ),
        )


class CostShortcutApply(PublicData):
    value: float
    date_override: date | None = None


class ReorderPositionsRequestBody(PublicData):
    """Request Body to reposition cost shortcuts."""

    id: int
    ui_position_index: int
