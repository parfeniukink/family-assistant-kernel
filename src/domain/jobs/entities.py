from datetime import datetime
from typing import Any

from pydantic import Field

from src.domain.entities import InternalData


class Job(InternalData):
    id: int
    name: str
    job_type: str
    metadata: dict[str, Any] = Field(alias="_metadata")
    interval_minutes: int | None = None
    is_active: bool
    last_run_at: datetime | None
    next_run_at: datetime
    last_status: str | None
    last_error: str | None
    run_count: int
    created_at: datetime
    user_id: int
