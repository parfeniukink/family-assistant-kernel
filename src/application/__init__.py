"""
Application layer — bridge between Presentation and the rest of the app.

It basically represents all the operations in the whole application on
the top level.

Each component in this layer defines specific operations that are
allowed to be performed by the user of this system in general.
"""

__all__ = (
    "JobType",
    "add_cost",
    "add_cost_shortcut",
    "add_income",
    "all_job_types",
    "apply_cost_shortcut",
    "authorize",
    "currency_exchange",
    "delete_cost",
    "delete_cost_shortcut",
    "delete_currency_exchange",
    "delete_income",
    "get_cost_shortcuts",
    "get_costs",
    "get_currency_exchanges",
    "get_incomes",
    "get_job_type",
    "get_tokens_pair",
    "jobs_scheduler",
    "lifespan_event",
    "notify_about_big_cost",
    "notify_about_income",
    "refresh_tokens",
    "transactions_basic_analytics",
    "update_cost",
    "update_income",
    "user_notifications",
    "user_notifications_count",
    "user_retrieve",
    "update_user_configuration",
)


from .analytics import transactions_basic_analytics
from .authentication import authorize, get_tokens_pair, refresh_tokens
from .notifications import (
    notify_about_big_cost,
    notify_about_income,
    user_notifications,
    user_notifications_count,
)
from .scheduler import (
    JobType,
    all_job_types,
    get_job_type,
    jobs_scheduler,
    lifespan_event,
)
from .transactions import (
    add_cost,
    add_cost_shortcut,
    add_income,
    apply_cost_shortcut,
    currency_exchange,
    delete_cost,
    delete_cost_shortcut,
    delete_currency_exchange,
    delete_income,
    get_cost_shortcuts,
    get_costs,
    get_currency_exchanges,
    get_incomes,
    update_cost,
    update_income,
)
from .users import update_user_configuration, user_retrieve
