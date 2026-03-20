"""Pipeline observability: trace ID + summary table.

Two ContextVars let agent helpers auto-record stats and tag logs
without signature changes:

    get_trace_id() -> str | None   — for log prefixes
    get_tracer()   -> Tracer | None — for recording stats

Outside a pipeline context (e.g. in tests), both return None.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import perf_counter
from uuid import uuid4

from loguru import logger

try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None  # type: ignore[assignment]

from src.domain.analytics.pricing import estimate_pipeline_cost
from src.infrastructure.agents import AGENT_MODELS
from src.infrastructure.repositories import AnalyticsAI

_trace_id: ContextVar[str | None] = ContextVar("_trace_id", default=None)
_tracer: ContextVar["Tracer | None"] = ContextVar("_tracer", default=None)


def get_trace_id() -> str | None:
    return _trace_id.get()


def get_tracer() -> "Tracer | None":
    return _tracer.get()


@dataclass
class AgentStat:
    agent: str
    elapsed: float
    error: bool = False


@dataclass
class Tracer:
    name: str
    trace_id: str
    user_id: int | None = None
    _stats: list[AgentStat] = field(default_factory=list)
    _meta: dict[str, int] = field(default_factory=dict)
    _t0: float = field(default_factory=perf_counter)

    def set_meta(self, key: str, value: int) -> None:
        self._meta[key] = value

    def record(
        self, agent: str, elapsed: float, *, error: bool = False
    ) -> None:
        self._stats.append(
            AgentStat(agent=agent, elapsed=elapsed, error=error)
        )

    def _aggregate(
        self,
    ) -> tuple[dict[str, dict], int, int]:
        """Aggregate per-agent stats."""

        agg: dict[str, dict] = {}
        total_calls = 0
        total_errors = 0
        for s in self._stats:
            if s.agent not in agg:
                agg[s.agent] = {
                    "calls": 0,
                    "total": 0.0,
                    "errors": 0,
                }
            agg[s.agent]["calls"] += 1
            agg[s.agent]["total"] += s.elapsed
            total_calls += 1
            if s.error:
                agg[s.agent]["errors"] += 1
                total_errors += 1
        return agg, total_calls, total_errors

    def log_summary(self) -> None:
        tid = self.trace_id
        wall = perf_counter() - self._t0

        if not self._stats:
            logger.info(
                f"Pipeline '{self.name}' (trace={tid}) "
                f"completed in {wall:.2f}s — no agent calls"
            )
            return

        agg, total_calls, total_errors = self._aggregate()

        # Build bordered table
        h = (
            f"{'Agent':<14}{'Calls':>7}"
            f"{'Total(s)':>10}{'Avg(s)':>9}{'Errors':>8}"
        )
        w = len(h)
        title = f" {self.name} (trace={tid}) "
        pad = max(w - len(title), 0)
        top = (
            f"\u250c{'─' * (pad // 2)}{title}"
            f"{'─' * (pad - pad // 2)}\u2510"
        )
        sep = f"\u251c{'─' * w}\u2524"
        bot = f"\u2514{'─' * w}\u2518"

        rows = [top, f"\u2502{h}\u2502", sep]
        for agent, d in agg.items():
            avg = d["total"] / d["calls"] if d["calls"] else 0
            row = (
                f"{agent:<14}{d['calls']:>7}"
                f"{d['total']:>10.2f}{avg:>9.2f}"
                f"{d['errors']:>8}"
            )
            rows.append(f"\u2502{row}\u2502")

        footer = (
            f" {total_calls} calls | " f"{total_errors} errors | {wall:.2f}s "
        )
        fpad = max(w - len(footer), 0)
        rows.append(sep)
        rows.append(
            f"\u2502{' ' * (fpad // 2)}{footer}"
            f"{' ' * (fpad - fpad // 2)}\u2502"
        )

        if self._meta:
            rows.append(sep)
            for mk, mv in self._meta.items():
                mrow = f"  {mk:<30}{mv:>14}  "
                mrow = mrow[:w].ljust(w)
                rows.append(f"\u2502{mrow}\u2502")

        rows.append(bot)

        logger.success("\n".join(rows))

    async def _persist(self) -> None:
        """Fire-and-forget save to analytics_ai."""

        if not self._stats:
            return

        try:
            agg, total_calls, total_errors = self._aggregate()
            wall = perf_counter() - self._t0

            stats_list = [
                {
                    "agent": agent,
                    "calls": d["calls"],
                    "total_s": round(d["total"], 2),
                    "avg_s": round(
                        d["total"] / d["calls"] if d["calls"] else 0,
                        2,
                    ),
                    "errors": d["errors"],
                }
                for agent, d in agg.items()
            ]

            cost = estimate_pipeline_cost(stats_list, AGENT_MODELS)
            repo = AnalyticsAI()
            await repo.save_run(
                pipeline_name=self.name,
                trace_id=self.trace_id,
                agent_stats=stats_list,
                total_calls=total_calls,
                total_errors=total_errors,
                wall_time_s=round(wall, 2),
                estimated_cost=round(cost, 6),
                user_id=self.user_id,
            )
            await repo.flush()
        except Exception as e:
            logger.warning(f"Failed to persist analytics: {e}")


@asynccontextmanager
async def pipeline_tracer(
    name: str, *, user_id: int | None = None
) -> AsyncIterator[Tracer]:
    tid = uuid4().hex[:12]
    tracer = Tracer(name=name, trace_id=tid, user_id=user_id)

    tok_id = _trace_id.set(tid)
    tok_tracer = _tracer.set(tracer)

    try:
        if sentry_sdk is not None:
            sentry_sdk.set_tag("pipeline_trace_id", tid)
            sentry_sdk.set_tag("pipeline_name", name)

        yield tracer
    finally:
        tracer.log_summary()
        await tracer._persist()
        _trace_id.reset(tok_id)
        _tracer.reset(tok_tracer)
