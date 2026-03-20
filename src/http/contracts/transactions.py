import contextlib
import functools
from datetime import date
from typing import Self

from pydantic import Field, field_validator, model_validator

from src import domain
from src.infrastructure import database
from src.infrastructure.responses import PublicData

from ._mixins import _TimestampValidationMixin, _ValueValidationMixin
from .currency import Currency


class Transaction(PublicData):
    """a public representation of any sort of a transaction in
    the system: cost, income, exchange.

    notes:
        This class is mostly for the analytics.
    """

    id: int = Field(description="Internal id of the cost/income/exchange.")
    operation: domain.transactions.OperationType = Field(
        description="The type of the operation"
    )
    name: str = Field(description="The name of the transaction")
    icon: str = Field(
        description="The icon of the transaction", min_length=1, max_length=1
    )
    value: float = Field(description="The amount with cents")
    timestamp: date = Field(
        description=(
            "Define the timestamp for the cost. The default value is 'now'"
        ),
    )
    currency: str = Field(description="The sign of the currency")
    user: str = Field(description="Transaction issuer")

    @functools.singledispatchmethod
    @classmethod
    def from_instance(cls, instance) -> "Transaction":
        raise NotImplementedError(
            f"Can not convert {type(instance)} into the Equity contract"
        )

    @from_instance.register
    @classmethod
    def _(cls, instance: domain.transactions.Transaction):
        return cls(
            id=instance.id,
            operation=instance.operation,
            name=instance.name,
            icon=instance.icon[0],
            value=domain.transactions.pretty_money(instance.value),
            timestamp=instance.timestamp,
            currency=instance.currency.sign,
            user=instance.user,
        )


class CostCategoryCreateBody(PublicData):
    """The request body to create a new cost category."""

    name: str


class CostCategory(CostCategoryCreateBody):
    """The public representation of a cost category."""

    id: int


class CostCreateBody(
    PublicData, _ValueValidationMixin, _TimestampValidationMixin
):
    """The request body to create a new cost."""

    name: str = Field(description="The name of the cost")
    value: float = Field(examples=[12.2, 650])
    timestamp: date = Field(
        default_factory=date.today,
        description=(
            "Define the timestamp for the cost. The default value is 'today'"
        ),
    )
    currency_id: int
    category_id: int

    @property
    def value_in_cents(self) -> int:
        return domain.transactions.cents_from_raw(self.value)


class CostUpdateBody(
    PublicData, _ValueValidationMixin, _TimestampValidationMixin
):
    """The request body to update the existing cost."""

    name: str | None = Field(
        default=None,
        description="The name of the currency",
    )
    value: float | None = Field(default=None, examples=[12.2, 650])
    timestamp: date | None = Field(
        default=None,
        description=(
            "Define the timestamp for the cost. The default value is 'null'"
        ),
    )
    currency_id: int | None = Field(
        default=None,
        description=(
            "A new currency id. Must be different from the previous one"
        ),
    )
    category_id: int | None = Field(
        default=None,
        description=(
            "A new currency id. Must be different from the previous one"
        ),
    )

    @property
    def value_in_cents(self) -> int | None:
        with contextlib.suppress(ValueError):
            return domain.transactions.cents_from_raw(self.value)

        return None


class Cost(PublicData):
    """The public representation of a cost."""

    id: int = Field(description="Unique identifier in the system")
    name: str = Field(description="The name of the cost")
    value: float = Field(examples=[12.2, 650])
    timestamp: date = Field(description="The date of a transaction")
    user: str = Field(description="The user representation")
    currency: Currency
    category: CostCategory

    @functools.singledispatchmethod
    @classmethod
    def from_instance(cls, instance) -> "Cost":
        raise NotImplementedError(
            f"Can not convert {type(instance)} "
            f"into the {type(cls.__name__)} contract"
        )

    @from_instance.register
    @classmethod
    def _(cls, instance: database.Cost):
        return cls(
            id=instance.id,
            name=instance.name,
            value=domain.transactions.pretty_money(instance.value),
            timestamp=instance.timestamp,
            user=instance.user.name,
            currency=Currency.model_validate(instance.currency),
            category=CostCategory.model_validate(instance.category),
        )


class IncomeCreateBody(
    PublicData, _ValueValidationMixin, _TimestampValidationMixin
):
    """The request body to create a new income."""

    name: str = Field(description="The name of the income")
    value: float = Field(examples=[12.2, 650])
    source: domain.transactions.IncomeSource = Field(
        default="revenue", description="Available 'source' for the income."
    )
    timestamp: date = Field(
        default_factory=date.today,
        description=("The date of a transaction"),
    )
    currency_id: int = Field(description="Internal currency system identifier")

    @property
    def value_in_cents(self) -> int:
        """return the value but in cents."""

        return domain.transactions.as_cents(self.value)


class IncomeUpdateBody(
    PublicData, _ValueValidationMixin, _TimestampValidationMixin
):
    """The request body to update the existing income."""

    name: str | None = Field(
        default=None,
        description="The name of the income",
    )
    value: float | None = Field(default=None, examples=[12.2, 650])
    source: domain.transactions.IncomeSource | None = Field(
        default=None,
        description="The income source",
    )
    timestamp: date | None = Field(
        default=None,
        description=(
            "Define the timestamp for the cost. The default value is 'now'"
        ),
    )
    currency_id: int | None = Field(
        default=None,
        description=(
            "A new currency id. Must be different from the previous one"
        ),
    )

    @property
    def value_in_cents(self) -> int | None:
        with contextlib.suppress(ValueError):
            return domain.transactions.cents_from_raw(self.value)

        return None


class Income(PublicData):
    """The public representation of an income."""

    id: int = Field(description="Unique identifier in the system")
    name: str = Field(description="The name of the income")
    value: float = Field(examples=[12.2, 650])
    source: domain.transactions.IncomeSource = Field(
        description="Available 'source' for the income."
    )
    timestamp: date = Field(description=("The date of a transaction"))
    user: str = Field(description="The user representation")
    currency: Currency

    @functools.singledispatchmethod
    @classmethod
    def from_instance(cls, instance) -> "Income":
        raise NotImplementedError(
            f"Can not convert {type(instance)} "
            f"into the {type(cls.__name__)} contract"
        )

    @from_instance.register
    @classmethod
    def _(cls, instance: database.Income):
        # TODO: ``instance.source`` is not just a `Literal` type.
        #       provide a proper type validation.

        return cls(
            id=instance.id,
            name=instance.name,
            value=domain.transactions.pretty_money(instance.value),
            source=instance.source,
            timestamp=instance.timestamp,
            user=instance.user.name,
            currency=Currency.model_validate(instance.currency),
        )


class ExchangeCreateBody(PublicData, _TimestampValidationMixin):
    """The request body to create a new income."""

    from_value: float = Field(description="Given value")
    to_value: float = Field(description="Received value")
    timestamp: date = Field(
        default_factory=date.today, description=("The date of a transaction")
    )
    from_currency_id: int = Field(
        description="Internal currency system identifier"
    )
    to_currency_id: int = Field(
        description="Internal currency system identifier"
    )

    @model_validator(mode="after")
    def validate_different_currencies(self) -> Self:
        if self.from_currency_id == self.to_currency_id:
            raise ValueError("Currencies must be different")
        else:
            return self

    @property
    def from_value_in_cents(self) -> int:
        """return the `from_value` but in cents."""

        return int(self.from_value * 100)

    @property
    def to_value_in_cents(self) -> int:
        """return the `to_value` but in cents."""

        return int(self.to_value * 100)

    @field_validator("from_value", "to_value", mode="before")
    @classmethod
    def _validate_money_values(cls, value: float) -> float:
        """check if the value is convertable to cents."""

        domain.transactions.cents_from_raw(value)
        return value


class Exchange(PublicData):
    """The public representation of an income."""

    id: int = Field(description="Unique identifier in the system")
    from_value: float = Field(description="Given value")
    to_value: float = Field(description="Received value")
    timestamp: date = Field(description=("The date of a transaction"))
    user: str = Field(description="The user representation")
    from_currency: Currency
    to_currency: Currency

    @functools.singledispatchmethod
    @classmethod
    def from_instance(cls, instance) -> "Exchange":
        raise NotImplementedError(
            f"Can not convert {type(instance)} "
            f"into the {type(cls.__name__)} contract"
        )

    @from_instance.register
    @classmethod
    def _(cls, instance: database.Exchange):
        return cls(
            id=instance.id,
            from_value=domain.transactions.pretty_money(instance.from_value),
            to_value=domain.transactions.pretty_money(instance.to_value),
            timestamp=instance.timestamp,
            user=instance.user.name,
            from_currency=Currency.model_validate(instance.from_currency),
            to_currency=Currency.model_validate(instance.to_currency),
        )
