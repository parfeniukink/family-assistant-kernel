import asyncio
import io
from unittest.mock import MagicMock, patch

import pytest
from loguru import logger

from src.infrastructure.tracing import (
    Tracer,
    get_trace_id,
    get_tracer,
    pipeline_tracer,
)


@pytest.fixture(autouse=True)
def _enable_tracing_logger():
    """Re-enable loguru for the tracing module (disabled by conftest)."""
    logger.enable("src.infrastructure.tracing")
    yield
    logger.disable("src.infrastructure.tracing")


# ── get_trace_id / get_tracer outside pipeline ──


def test_get_trace_id_without_pipeline():
    assert get_trace_id() is None


def test_get_tracer_without_pipeline():
    assert get_tracer() is None


# ── pipeline_tracer sets and resets ──


async def test_pipeline_tracer_sets_and_resets_trace_id():
    assert get_trace_id() is None

    async with pipeline_tracer("test"):
        tid = get_trace_id()
        assert tid is not None
        assert len(tid) == 12

    assert get_trace_id() is None


async def test_pipeline_tracer_sets_and_resets_tracer():
    assert get_tracer() is None

    async with pipeline_tracer("test") as tracer:
        assert get_tracer() is tracer
        assert isinstance(tracer, Tracer)

    assert get_tracer() is None


# ── Tracer.record + log_summary ──


async def test_tracer_record_and_summary():
    sink = io.StringIO()
    handler_id = logger.add(sink, format="{message}")

    try:
        async with pipeline_tracer("unit") as tracer:
            tracer.record("filter", 1.23)
            tracer.record("filter", 0.45)
            tracer.record("merge", 2.10)
            tracer.record("inference", 3.00, error=True)

        output = sink.getvalue()

        assert tracer.trace_id in output
        assert "filter" in output
        assert "merge" in output
        assert "inference" in output
        assert "4 calls" in output
        assert "1 errors" in output
        # Box-drawing borders
        assert "\u250c" in output
        assert "\u2514" in output
    finally:
        logger.remove(handler_id)


async def test_tracer_empty_stats():
    sink = io.StringIO()
    handler_id = logger.add(sink, format="{message}")

    try:
        async with pipeline_tracer("empty"):
            pass

        output = sink.getvalue()
        assert "no agent calls" in output
    finally:
        logger.remove(handler_id)


# ── Trace ID isolation across concurrent pipelines ──


async def test_trace_id_isolation():
    seen: dict[str, str] = {}

    async def run(name: str):
        async with pipeline_tracer(name):
            tid = get_trace_id()
            assert tid is not None
            seen[name] = tid
            await asyncio.sleep(0.01)
            assert get_trace_id() == tid

    await asyncio.gather(run("a"), run("b"))

    assert seen["a"] != seen["b"]
    assert get_trace_id() is None


# ── Sentry tags ──


async def test_sentry_tags_set():
    mock_sentry = MagicMock()

    with patch("src.infrastructure.tracing.sentry_sdk", mock_sentry):
        async with pipeline_tracer("sentry-test"):
            pass

    calls = {c.args[0]: c.args[1] for c in mock_sentry.set_tag.call_args_list}
    assert "pipeline_trace_id" in calls
    assert "pipeline_name" in calls
    assert calls["pipeline_name"] == "sentry-test"


# ── Meta rendering ──


async def test_tracer_meta_in_summary():
    sink = io.StringIO()
    handler_id = logger.add(sink, format="{message}")

    try:
        async with pipeline_tracer("meta") as tracer:
            tracer.record("agent", 1.0)
            tracer.set_meta("candidates", 45)
            tracer.set_meta("cache_dedup", -12)
            tracer.set_meta("\u2192 to_agent", 28)

        output = sink.getvalue()

        assert "candidates" in output
        assert "45" in output
        assert "cache_dedup" in output
        assert "-12" in output
        assert "\u2192 to_agent" in output
        assert "28" in output
    finally:
        logger.remove(handler_id)


async def test_tracer_no_meta_no_extra_section():
    sink = io.StringIO()
    handler_id = logger.add(sink, format="{message}")

    try:
        async with pipeline_tracer("no-meta") as tracer:
            tracer.record("agent", 1.0)

        output = sink.getvalue()
        assert output.count("\u251c") == 2
    finally:
        logger.remove(handler_id)
