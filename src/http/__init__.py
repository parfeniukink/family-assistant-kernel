"""
PRESENTATION TIER.

what HTTP-resources groups we have:
1. auth - JWT authentication (login, refresh, logout)
2. users - related to actions what John does to clients
3. costs - allows clients to manage their 'cost' transactions.
    the MOST FREQUENTLY USED REQUEST for John.
4. incomes - allows clients to manage their 'income' transactions.
5. exchange - allows clients to manage their 'currency exchanges' trns-ns.
    when clients exchange money from one currency to another
6. analytics - allows clients to claim analytics based on the trns-ns.
    this group is also about getting information about the EQUITY.
"""

from .contracts import (
    Cost,
    CostCategory,
    CostCategoryCreateBody,
    CostCreateBody,
    CostShortcut,
    CostShortcutApply,
    CostShortcutCreateBody,
    CostUpdateBody,
    Currency,
    CurrencyCreateBody,
    Equity,
    Exchange,
    ExchangeCreateBody,
    Income,
    IncomeCreateBody,
    IncomeUpdateBody,
    Job,
    JobCreateBody,
    JobType,
    JobUpdateBody,
    NewsItem,
    Transaction,
    TransactionBasicAnalytics,
    User,
    UserConfigurationPartialUpdateRequestBody,
    UserCreateRequestBody,
)
from .resources.analytics import router as analytics_router
from .resources.costs import router as costs_router
from .resources.currencies import router as currencies_router
from .resources.exchange import router as exchange_router
from .resources.identity import router as users_router
from .resources.incomes import router as incomes_router
from .resources.jobs import router as jobs_router
from .resources.news import router as news_router
from .resources.notifications import router as notifications_router
from .resources.transactions import router as transactions_router
