"""Jobs scheduler — type-based trampolines.

Each registered job type gets one trampoline — a long-running
asyncio task that repeatedly executes the handler and sleeps.

Two trampoline flavours:
  _kernel_trampoline  Code-defined, no DB record.
                      Fixed interval, never stops.
  _trampoline         DB-backed, one loop per job type.
                      Polls for due jobs, self-terminates
                      when none remain active.

Public API:
  schedule_type(jt)   Start/restart the trampoline for *jt*.
  run_now(job)        Execute a single DB job immediately.
  bootstrap()         Start all trampolines at app startup.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from loguru import logger

from src.domain.jobs.registry import JobType, all_job_types, get_job_type
from src.domain.jobs.value_objects import JobContext
from src.infrastructure import database, repositories

from . import _primitives as primitives


class JobsScheduler:
    """Owns the trampoline lifecycle.

    Call ``bootstrap`` once at startup; after that, call
    ``schedule_type`` whenever a new user job is created
    or reactivated so its trampoline is (re)started.
    """

    def schedule_type(self, job_type_definition: JobType) -> None:
        """Start (or restart) a trampoline for a job type."""

        jt = job_type_definition.job_type
        logger.success(f"Scheduling `{jt}` jobs")

        trampoline = (
            self._kernel_trampoline(job_type_definition)
            if job_type_definition.is_kernel
            else self._trampoline(job_type_definition)
        )
        primitives.run_task(f"trampoline:{jt}", trampoline)

    def run_now(self, job: database.Job) -> None:
        """Execute a single job immediately via the queue."""

        job_type_definition = get_job_type(job.job_type)
        if job_type_definition is None:
            logger.warning(
                f"Job type '{job.job_type}' not found " f"for job {job.id}"
            )
            return

        primitives.submit(
            name=f"manual:{job.job_type}:{job.id}",
            handler=lambda: self._execute_batch(job_type_definition, [job]),
        )

    async def bootstrap(self) -> None:
        """Start all trampolines: kernel from registry,
        user from database."""

        # NOTE: Kernel jobs (no DB record)
        for jt in all_job_types().values():
            if jt.is_kernel:
                logger.success(
                    f"Starting kernel job `{jt.name}` "
                    f"(every {jt.interval_minutes}min)"
                )
                self.schedule_type(jt)

        # NOTE: User jobs (DB-backed)
        repo = repositories.Job()
        reset = await repo.reset_stale_running_jobs()
        if reset:
            logger.warning(f"Reset {reset} stale running job(s)")

        jobs = await repo.active_jobs()
        types_with_jobs: set[str] = {j.job_type for j in jobs}
        for job_type in types_with_jobs:
            jt_def = get_job_type(job_type)
            if jt_def is None:
                logger.warning(f"No handler for type '{job_type}'")
                continue
            if jt_def.is_kernel:
                continue  # already started
            count = sum(1 for j in jobs if j.job_type == job_type)
            logger.info(f"Found {count} active job(s) for `{job_type}`")
            self.schedule_type(jt_def)

    async def _kernel_trampoline(self, job_type_definition: JobType) -> None:
        """Trampoline for kernel jobs: execute → sleep → repeat.
        No DB interaction. Never self-terminates."""

        assert job_type_definition.interval_minutes is not None

        while True:
            try:
                await job_type_definition.handler()
            except Exception as error:
                logger.error(
                    f"Kernel job `{job_type_definition.name}`"
                    f" failed: {error}"
                )
            await asyncio.sleep(job_type_definition.interval_minutes * 60)

    async def _trampoline(self, job_type_definition: JobType) -> None:
        """Trampoline for DB-backed jobs: poll due jobs →
        execute batch → sleep → repeat.
        Self-terminates when no active jobs remain."""

        name = f"trampoline:{job_type_definition.job_type}"

        while True:
            repo = repositories.Job()
            jobs = await repo.active_jobs_by_type(job_type_definition.job_type)

            if not jobs:
                logger.info(f"Trampoline {name}: " f"no active jobs, stopping")
                return

            # Only consider jobs with a scheduled interval
            scheduled = [
                job for job in jobs if (job.interval_minutes or 0) > 0
            ]
            if not scheduled:
                logger.info(
                    f"Trampoline {name}: "
                    f"all jobs are manual-only, stopping"
                )
                return

            now = datetime.now(timezone.utc)
            due_jobs = [job for job in scheduled if job.next_run_at <= now]

            if due_jobs:
                logger.info(
                    f"Trampoline {name}: " f"executing {len(due_jobs)} job(s)"
                )
                await self._execute_batch(job_type_definition, due_jobs)

            min_interval = min(
                (job.interval_minutes or 0) for job in scheduled
            )
            await asyncio.sleep(min_interval * 60)

    async def _execute_batch(
        self,
        job_type_definition: JobType,
        jobs: list[database.Job],
    ) -> None:
        """Run the handler for each job, update status in DB.
        On error the job is paused (is_active=False)."""

        for job in jobs:
            repo = repositories.Job()
            await repo.update_job_status(job.id, last_status="running")
            await repo.flush()

            now = datetime.now(timezone.utc)

            try:
                assert job_type_definition.parameters_model is not None
                params = job_type_definition.parameters_model(**job._metadata)
                context = JobContext(
                    job_id=job.id,
                    user_id=job.user_id,
                    job_name=job.name,
                )
                await job_type_definition.handler(params, context)
                status, error = "success", None
            except Exception as e:
                logger.error(
                    f"Job {job.id} "
                    f"({job_type_definition.job_type}) "
                    f"failed: {e}"
                )
                status, error = "error", str(e)[:1000]

            update_kwargs: dict = dict(
                last_run_at=now,
                last_status=status,
                last_error=error,
                run_count=job.run_count + 1,
            )

            interval = job.interval_minutes or 0
            if interval > 0:
                update_kwargs["next_run_at"] = now + timedelta(
                    minutes=interval
                )
            if error:
                update_kwargs["is_active"] = False
                logger.warning(
                    f"Job {job.id} "
                    f"({job_type_definition.job_type}) "
                    f"paused due to error: {error[:200]}"
                )

            repo = repositories.Job()
            await repo.update_job_status(job.id, **update_kwargs)
            await repo.flush()


jobs_scheduler = JobsScheduler()
