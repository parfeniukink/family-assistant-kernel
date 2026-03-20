from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from sqlalchemy import Result, Select, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure import database, errors


class Job(database.DataAccessLayer):
    """Data access for scheduled jobs."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        super().__init__(session)

    async def jobs_for_user(
        self, user_id: int
    ) -> AsyncGenerator[database.Job, None]:
        query: Select = (
            select(database.Job)
            .where(database.Job.user_id == user_id)
            .order_by(database.Job.id)
        )

        async with self._read_session() as session:
            results: Result = await session.execute(query)
            for item in results.scalars():
                yield item

    async def active_jobs(self) -> list[database.Job]:
        """All active jobs."""

        query: Select = select(database.Job).where(
            database.Job.is_active.is_(True),
        )

        async with self._read_session() as session:
            results: Result = await session.execute(query)
            return list(results.scalars().all())

    async def active_jobs_by_type(self, job_type: str) -> list[database.Job]:
        """All active jobs of a given type."""

        query: Select = select(database.Job).where(
            database.Job.is_active.is_(True),
            database.Job.job_type == job_type,
        )

        async with self._read_session() as session:
            results: Result = await session.execute(query)
            return list(results.scalars().all())

    async def job_by_name(
        self, user_id: int, name: str
    ) -> database.Job | None:
        query = select(database.Job).where(
            database.Job.user_id == user_id,
            database.Job.name == name,
        )
        async with self._read_session() as session:
            result: Result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_job(self, job_id: int) -> database.Job | None:
        """Get a single job by ID (returns None if missing)."""

        query = select(database.Job).where(database.Job.id == job_id)

        async with self._read_session() as session:
            result: Result = await session.execute(query)
            return result.scalar_one_or_none()

    async def add_job(self, candidate: database.Job) -> database.Job:
        self._write_session.add(candidate)
        return candidate

    async def update_job(
        self, job_id: int, user_id: int, **values
    ) -> database.Job:
        query = (
            update(database.Job)
            .where(
                database.Job.id == job_id,
                database.Job.user_id == user_id,
            )
            .values(**values)
            .returning(database.Job)
        )

        result = await self._write_session.execute(query)
        row = result.scalar_one_or_none()
        if row is None:
            raise errors.NotFoundError(f"Job {job_id} not found")
        return row

    async def update_job_status(self, job_id: int, **values) -> None:
        query = (
            update(database.Job)
            .where(database.Job.id == job_id)
            .values(**values)
        )
        await self._write_session.execute(query)

    async def delete_job(self, user_id: int, job_id: int) -> None:
        query = (
            delete(database.Job)
            .where(
                database.Job.id == job_id,
                database.Job.user_id == user_id,
            )
            .returning(database.Job.id)
        )

        result = await self._write_session.execute(query)
        if result.scalar_one_or_none() is None:
            raise errors.NotFoundError(f"Job {job_id} not found")

    async def reset_stale_running_jobs(
        self, now: datetime | None = None
    ) -> int:
        """Reset jobs stuck as 'running' longer than their interval.
        Returns the number of jobs reset."""

        now = now or datetime.now(timezone.utc)

        # A job is stale if it's "running" but next_run_at
        # is already in the past (it missed its window).
        query = (
            update(database.Job)
            .where(
                database.Job.last_status == "running",
                database.Job.next_run_at <= now,
            )
            .values(last_status="stale", next_run_at=now)
            .returning(database.Job.id)
        )

        async with self._read_session() as session:
            async with session.begin():
                result = await session.execute(query)
                return len(result.all())
