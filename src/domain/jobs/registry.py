from collections.abc import Callable, Coroutine
from typing import Any, get_type_hints

from pydantic import BaseModel

from .value_objects import JobContext, JobType

# NOTE: Global Registry implementation
_REGISTRY: dict[str, JobType] = {}


def register_job_type(
    label: str,
    *,
    name: str | None = None,
    interval_minutes: int | None = None,
) -> Callable:
    def decorator(
        func: Callable[..., Coroutine[Any, Any, None]],
    ) -> Callable[..., Coroutine[Any, Any, None]]:
        desc = (func.__doc__ or "").strip()
        if not desc:
            raise ValueError(f"Handler {func.__name__} must have a docstring")

        if label == "kernel":
            if not name:
                raise ValueError(
                    f"Handler {func.__name__}: kernel jobs "
                    f"must have an explicit name"
                )
            if not interval_minutes:
                raise ValueError(
                    f"Handler {func.__name__}: kernel jobs "
                    f"must have interval_minutes"
                )
            params_type = None
        else:
            hints = get_type_hints(func)
            params_type = hints.get("params")
            if params_type is None or not (
                isinstance(params_type, type)
                and issubclass(params_type, BaseModel)
            ):
                raise ValueError(
                    f"Handler {func.__name__}: first param "
                    f"must be typed as a BaseModel subclass"
                )

            context_type = hints.get("context")
            if context_type is not JobContext:
                raise ValueError(
                    f"Handler {func.__name__}: second param "
                    f"must be typed as JobContext"
                )

        if label == "system" and not name:
            raise ValueError(
                f"Handler {func.__name__}: system jobs "
                f"must have an explicit name"
            )

        job_type = func.__name__

        jt = JobType(
            job_type=job_type,
            label=label,
            name=name or job_type.replace("_", " ").title(),
            description=desc,
            is_kernel=(label == "kernel"),
            parameters_model=params_type,
            interval_minutes=interval_minutes,
            handler=func,
        )
        _REGISTRY[job_type] = jt
        return func

    return decorator


def get_job_type(job_type: str) -> JobType | None:
    return _REGISTRY.get(job_type)


def all_job_types() -> dict[str, JobType]:
    return dict(_REGISTRY)
