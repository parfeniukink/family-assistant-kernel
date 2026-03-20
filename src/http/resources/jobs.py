from fastapi import APIRouter, Body, Depends, status
from pydantic import ValidationError

from src import application as op
from src import domain
from src.infrastructure import ResponseMulti, database, repositories

from ..contracts import jobs as contracts

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("/actions")
async def actions_list(
    _=Depends(op.authorize),
) -> ResponseMulti[contracts.JobType]:
    job_types: dict[str, domain.jobs.JobType] = domain.jobs.all_job_types()

    return ResponseMulti[contracts.JobType](
        result=[
            contracts.JobType(
                job_type=job_type.job_type,
                label=job_type.label,
                name=job_type.name,
                description=job_type.description,
                parameters_schema=(
                    job_type.parameters_model.model_json_schema()
                ),
                interval_required=True,
            )
            for job_type in job_types.values()
            if (not job_type.is_kernel)
            and (job_type.parameters_model is not None)
        ]
    )


@router.get("", status_code=status.HTTP_200_OK)
async def jobs_list(
    user: domain.users.User = Depends(op.authorize),
) -> ResponseMulti[contracts.Job]:
    return ResponseMulti[contracts.Job](
        result=[
            contracts.Job.from_instance(item)
            async for item in (
                repositories.Job().jobs_for_user(user_id=user.id)
            )
        ]
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def job_create(
    user: domain.users.User = Depends(op.authorize),
    body: contracts.JobCreateBody = Body(...),
) -> None:
    job_type_definition = op.get_job_type(body.job_type)
    if job_type_definition is None:
        raise ValueError(f"Unknown job type: {body.job_type}")

    if job_type_definition.is_kernel:
        raise ValueError("Kernel jobs cannot be created via API")

    # System jobs use the registered name; others require it
    job_name = body.name
    if job_type_definition.label == "system":
        job_name = job_type_definition.name
    elif not job_name:
        raise ValueError("Name is required")

    repo = repositories.Job()
    existing = await repo.job_by_name(user_id=user.id, name=job_name)
    if existing:
        raise ValueError(f"Job with name '{job_name}' already exists")

    try:
        job_type_definition.parameters_model(
            **body.metadata,
        )  # type: ignore[misc]
    except ValidationError as e:
        raise ValueError(str(e))

    if not body.interval_minutes:
        raise ValueError("Interval is required")

    job = await repo.add_job(
        candidate=database.Job(
            name=job_name,
            job_type=body.job_type,
            _metadata=body.metadata,
            interval_minutes=body.interval_minutes,
            user_id=user.id,
        )
    )
    await repo.flush()

    if job.is_active:
        op.jobs_scheduler.schedule_type(job_type_definition)


@router.patch("/{job_id}", status_code=status.HTTP_200_OK)
async def job_update(
    job_id: int,
    user: domain.users.User = Depends(op.authorize),
    body: contracts.JobUpdateBody = Body(...),
) -> contracts.Job:
    values = body.json_body()
    if not values:
        raise ValueError("No fields to update")

    repo = repositories.Job()
    updated = await repo.update_job(job_id, user.id, **values)
    await repo.flush()

    # Ensure trampoline is running for this type
    jt_def = domain.jobs.get_job_type(updated.job_type)
    if jt_def is not None and updated.is_active:
        op.jobs_scheduler.schedule_type(jt_def)

    return contracts.Job.from_instance(updated)


@router.post(
    "/{job_id}/run",
    status_code=status.HTTP_202_ACCEPTED,
)
async def job_run(
    job_id: int,
    user: domain.users.User = Depends(op.authorize),
) -> dict:
    """Run a saved job immediately."""

    job = await repositories.Job().get_job(job_id)
    if job is None or job.user_id != user.id:
        raise ValueError(f"Job {job_id} not found")

    op.jobs_scheduler.run_now(job)

    return {"status": "submitted", "job_id": job_id}


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def job_delete(
    job_id: int,
    user: domain.users.User = Depends(op.authorize),
) -> None:
    repo = repositories.Job()
    await repo.delete_job(user_id=user.id, job_id=job_id)
    await repo.flush()
