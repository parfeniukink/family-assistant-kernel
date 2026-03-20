from datetime import date
from typing import NamedTuple

from sqlalchemy import Result, func, select
from sqlalchemy.sql.expression import cast
from sqlalchemy.types import Date

from src.infrastructure.database import AnalyticsAI, DataAccessLayer


class PipelineCostRow(NamedTuple):
    pipeline_name: str
    total_cost: float
    total_runs: int


class AnalyticsAIRepo(DataAccessLayer):
    async def save_run(
        self,
        *,
        pipeline_name: str,
        trace_id: str,
        agent_stats: list[dict],
        total_calls: int,
        total_errors: int,
        wall_time_s: float,
        estimated_cost: float,
        user_id: int | None = None,
    ) -> None:
        row = AnalyticsAI(
            pipeline_name=pipeline_name,
            trace_id=trace_id,
            agent_stats=agent_stats,
            total_calls=total_calls,
            total_errors=total_errors,
            wall_time_s=wall_time_s,
            estimated_cost=estimated_cost,
            user_id=user_id,
        )
        self._write_session.add(row)

    async def cost_per_pipeline(
        self,
        start_date: date,
        end_date: date,
    ) -> list[PipelineCostRow]:
        """Return (pipeline_name, total_cost, total_runs) grouped
        by pipeline within a date range."""

        day_col = cast(AnalyticsAI.created_at, Date)
        total_cost = func.sum(AnalyticsAI.estimated_cost)

        query = (
            select(
                AnalyticsAI.pipeline_name,
                total_cost,
                func.count(AnalyticsAI.id),
            )
            .where(day_col.between(start_date, end_date))
            .group_by(AnalyticsAI.pipeline_name)
            .order_by(total_cost.desc())
        )

        async with self._read_session() as session:
            result: Result = await session.execute(query)
            return [PipelineCostRow(*row) for row in result.all()]
