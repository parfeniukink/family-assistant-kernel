from collections.abc import Callable, Coroutine
from typing import Any

from pydantic import BaseModel

from src.domain.entities import InternalData


class JobContext(BaseModel):
    """Scheduler-injected execution context.
    Passed alongside params to every handler.
    """

    job_id: int
    user_id: int
    job_name: str


class JobType(InternalData):
    job_type: str
    label: str
    name: str
    description: str
    is_kernel: bool = False
    parameters_model: type[BaseModel] | None = None
    interval_minutes: int | None = None
    handler: Callable[..., Coroutine[Any, Any, None]]
