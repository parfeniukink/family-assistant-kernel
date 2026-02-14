"""
module with analytics contracts.

basically it represents some analytics by calculating values
of all the transactions, saved in the database for the specific dates range.
"""

import functools
import operator

from pydantic import Field, field_validator

from src import domain
from src.infrastructure import IncomeSource, PublicData

from .currency import Currency


class CostsByCategory(PublicData):
    """Represents expences for specific cost categories."""

    id: int = Field(description="The ID of the category", examples=[1, 2, 3])
    name: str = Field(
        description="The name of the category", examples=["Taxes"]
    )
    total: float = Field(description="The total for the selected category")
    ratio: float = Field(
        default=0.0, description="ratio=(sum(outboud) / sum(inbound)) * 100"
    )

    @field_validator("ratio", mode="after")
    @classmethod
    def _round_output_value(cls, value: float) -> float:
        """round to 1 decimal places."""

        return round(value, 1)


class CostsAnalytics(PublicData):
    """Represents costs analytics."""

    total: float = Field(description="The total number of costs")
    categories: list[CostsByCategory]


class IncomesBySource(PublicData):
    """Represents incomes for specific source."""

    source: IncomeSource = Field(
        description="The source name", examples=["revenue"]
    )
    total: float = Field(description="The total for the selected source")


class IncomesAnalytics(PublicData):
    total: float = Field(description="The total number of all incomes")
    sources: list[IncomesBySource] = Field(default_factory=list)


class TransactionBasicAnalytics(PublicData):
    """Per-currency analytics block."""

    currency: Currency
    costs: CostsAnalytics
    incomes: IncomesAnalytics
    from_exchanges: float = Field(
        description="The impact of currency exchange transactions"
    )

    @functools.singledispatchmethod
    @classmethod
    def from_instance(cls, instance) -> "TransactionBasicAnalytics":

        raise NotImplementedError(
            f"Can not get {cls.__name__} from {type(instance)} type"
        )

    @from_instance.register
    @classmethod
    def _(cls, instance: domain.transactions.TransactionsBasicAnalytics):
        costs_analytics = CostsAnalytics(
            total=domain.transactions.pretty_money(instance.costs.total),
            categories=[
                CostsByCategory(
                    id=item.id,
                    name=item.name,
                    total=domain.transactions.pretty_money(item.total),
                    ratio=item.ratio,
                )
                for item in sorted(
                    instance.costs.categories,
                    key=operator.attrgetter("ratio"),
                    reverse=True,
                )
                if item.total > 0
            ],
        )
        incomes_analytics = IncomesAnalytics(
            total=domain.transactions.pretty_money(instance.incomes.total),
            sources=[
                IncomesBySource(
                    source=item.source,
                    total=domain.transactions.pretty_money(item.total),
                )
                for item in instance.incomes.sources
            ],
        )

        return cls(
            currency=Currency.from_instance(instance.currency),
            costs=costs_analytics,
            incomes=incomes_analytics,
            from_exchanges=domain.transactions.pretty_money(
                instance.from_exchanges
            ),
        )


class TransactionAnalyticsResponse(PublicData):
    """Response model for transaction analytics endpoint."""

    result: list[TransactionBasicAnalytics]
    total_ratio: float = Field(
        description="Currency-independent ratio (all converted to USD)"
    )

    @field_validator("total_ratio", mode="after")
    @classmethod
    def _round_output_value(cls, value: float) -> float:
        """round to 1 decimal places."""

        return round(value, 1)
