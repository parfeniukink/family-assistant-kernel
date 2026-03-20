import functools
from datetime import datetime
from typing import Any

from pydantic import Field

from src.infrastructure import database
from src.infrastructure.responses import PublicData


class JobType(PublicData):
    """Represent a Job Type without a handler."""

    job_type: str
    label: str
    name: str
    description: str
    parameters_schema: dict[str, Any] | None = None
    interval_required: bool = False


class Job(PublicData):
    id: int
    name: str
    job_type: str
    metadata: dict[str, Any]
    interval_minutes: int | None = None
    is_active: bool
    last_run_at: datetime | None
    next_run_at: datetime
    last_status: str | None
    last_error: str | None
    run_count: int
    created_at: datetime

    @functools.singledispatchmethod
    @classmethod
    def from_instance(cls, instance) -> "Job":
        raise NotImplementedError(f"Can not convert {type(instance)} into Job")

    @from_instance.register
    @classmethod
    def _(cls, instance: database.Job):
        return cls(
            id=instance.id,
            name=instance.name,
            job_type=instance.job_type,
            metadata=instance._metadata,
            interval_minutes=instance.interval_minutes,
            is_active=instance.is_active,
            last_run_at=instance.last_run_at,
            next_run_at=instance.next_run_at,
            last_status=instance.last_status,
            last_error=instance.last_error,
            run_count=instance.run_count,
            created_at=instance.created_at,
        )


class JobCreateBody(PublicData):
    name: str | None = Field(default=None, max_length=255)
    job_type: str = Field(max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)
    interval_minutes: int | None = None


class JobUpdateBody(PublicData):
    name: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
