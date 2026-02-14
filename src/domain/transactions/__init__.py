"""
this package encapsulates all the available transactions:
* COST - because of 'costs'
* INCOME - because there are many 'income sources'
* EXCHANGE - because of 'currency exchange'

the 'Transaction' itself stands for a shared instance that
represents shared parameters for all types of operations.

in general, this module is about CURD operations of the next tables:
- currencies
- cost_categories
- costs
- incomes
- exchanges

also you can find the domain validation and other batteries in that package.
"""

__all__ = (
    "AnalyticsPeriod",
    "BasicAnalyticsResult",
    "Cost",
    "CostCategory",
    "CostsAnalytics",
    "CostsByCategory",
    "Exchange",
    "Income",
    "IncomesAnalytics",
    "OperationType",
    "Transaction",
    "Transaction",
    "TransactionRepository",
    "TransactionsBasicAnalytics",
    "TransactionsFilter",
    "as_cents",
    "cents_from_raw",
    "pretty_money",
    "timestamp_from_raw",
)

from .data_transformation import (
    as_cents,
    cents_from_raw,
    pretty_money,
    timestamp_from_raw,
)
from .entities import Cost, CostCategory, Exchange, Income
from .repository import TransactionRepository
from .value_objects import (
    AnalyticsPeriod,
    BasicAnalyticsResult,
    CostsAnalytics,
    CostsByCategory,
    IncomesAnalytics,
    OperationType,
    Transaction,
    TransactionsBasicAnalytics,
    TransactionsFilter,
)
