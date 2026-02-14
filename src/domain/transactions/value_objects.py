from datetime import date
from typing import Literal, Self

from pydantic import Field, model_validator

from src.domain.equity import Currency
from src.infrastructure import IncomeSource, InternalData

# represents the available list of query strings that client
# can specify instead of dates to get the basic analytics.
AnalyticsPeriod = Literal["current-month", "previous-month"]

OperationType = Literal["cost", "income", "exchange"]


class Transaction(InternalData):
    """represents the data structure across multiple database
    tables: 'incomes', 'costs', 'exchanges'.

    params:
        ``id`` the id of the cost or income or exchange.
        ``currency`` stands for the 'currency sign'. Ex: $, etc.
        ``icon`` is just a sign of an transaction.
                for costs - first character of category
                for incomes and exchanges - specific characters.

    notes:
        for the``exchange`` type of operation, the ``currency`` belongs
        to the ``exchanges.to_currency`` database parameter.
        the value that is going to be used is a sign of that currency.

        there is no reason to keep the ``id`` since they will be probably
        duplicated for different types of operations. nevertheless this
        is kept as 'Entity' instead of an 'Value object'.

        the ``id`` IS NOT unique.
    """

    id: int
    operation: OperationType
    icon: str
    name: str
    value: int
    timestamp: date
    currency: Currency
    user: str


class TransactionsFilter(InternalData):
    """This class is used to encapsulate filters for transactions fetching.

    WHAT DATA MEANS:
    (1) only_my: filter by authorized user
    (2) operation: optinally filter by transaction type
    (3) currency_id: optionally filter by Currency ID
    (4) cost_category_id: optionally filter by Cost Category ID
    (5) start_date: optionally specify Start Date
    (6) end_date: optionally specify End Date (default to Today)
    (7) period: optionally specify Period (instead of Start/End Dates)
    """

    only_mine: bool = False

    # TODO: Change to list[OperationType]
    operation: OperationType | None = None

    currency_id: int | None = None
    cost_category_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    period: AnalyticsPeriod | None = None
    pattern: str | None = None

    @model_validator(mode="after")
    def validate_dates_range(self) -> Self:
        dates_range_specified: bool = bool(self.start_date and self.end_date)

        if dates_range_specified and self.period:
            raise ValueError("You can NOT specify DATES RANGE and PERIOD")

        # todo: add more validation

        return self


# ==================================================
# analytics section
# ==================================================
class CostsByCategory(InternalData):
    """
    args:
        ``id`` - the ID of the cost category
        ``name`` - the name of the cost category
        ``total`` - the total for the selected category
        ``ratio`` - total / all costs total
    """

    id: int
    name: str
    total: int
    ratio: float


class CostsAnalytics(InternalData):
    """represents relative numbers for costs by their categories.

    args:
        ``total`` - sum of all the categories costs
    """

    categories: list[CostsByCategory] = Field(default_factory=list)
    total: int = 0


class IncomesBySource(InternalData):
    """
    args:
        ``source`` - the source of the income
        ``total`` - total by source

    todo:
        [ ] for the 'exchange' operation type expect only the ``to_value``
            in the analytics of the selected currency.

    notes:
        if the 'exchange' item is in the list - the operation type is revenue.
    """

    source: IncomeSource
    total: int


class IncomesAnalytics(InternalData):
    """just aggregates the data.

    args:
        ``total`` - the total of all incomes of all the sourcces
    """

    total: int = 0
    sources: list[IncomesBySource] = Field(default_factory=list)


class TransactionsBasicAnalytics(InternalData):
    """represents the analytics aggregated block by the currency.

    args:
        ``from_exchanges`` - absolute value in the range for the
            selected currency. it you got 100$ and gave 50$ in exchange
            process, the value would be 50 (because 100 - 50)
    """

    currency: Currency
    costs: CostsAnalytics = CostsAnalytics()
    incomes: IncomesAnalytics = IncomesAnalytics()
    from_exchanges: int = 0


class BasicAnalyticsResult(InternalData):
    """Result of basic analytics computation.

    Contains per-currency analytics and a currency-independent total ratio.
    """

    per_currency: tuple[TransactionsBasicAnalytics, ...]
    total_ratio: float
