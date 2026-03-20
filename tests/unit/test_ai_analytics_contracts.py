import json
from datetime import date

from src.http.contracts.analytics import (
    AiAnalyticsResponse,
    PipelineCostSummary,
)


def test_percentage_rounds_to_one_decimal():
    summary = PipelineCostSummary(
        pipeline_name="rss",
        total_cost=0.033333,
        total_runs=3,
        percentage=33.333,
    )
    assert summary.percentage == 33.3


def test_total_cost_rounds_to_six_decimals():
    summary = PipelineCostSummary(
        pipeline_name="rss",
        total_cost=0.0123456789,
        total_runs=1,
        percentage=100.0,
    )
    assert summary.total_cost == 0.012346


def test_zero_cost_percentage():
    summary = PipelineCostSummary(
        pipeline_name="rss",
        total_cost=0.0,
        total_runs=5,
        percentage=0.0,
    )
    assert summary.percentage == 0.0


def test_response_serializes_dates():
    resp = AiAnalyticsResponse(
        result=[],
        start_date=date(2026, 2, 16),
        end_date=date(2026, 3, 18),
    )
    body = json.loads(resp.model_dump_json(by_alias=True))
    assert body["startDate"] == "2026-02-16"
    assert body["endDate"] == "2026-03-18"


def test_response_camel_case_keys():
    resp = AiAnalyticsResponse(
        result=[
            PipelineCostSummary(
                pipeline_name="rss",
                total_cost=0.01,
                total_runs=2,
                percentage=100.0,
            )
        ],
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )
    body = json.loads(resp.model_dump_json(by_alias=True))
    item = body["result"][0]
    assert "pipelineName" in item
    assert "totalCost" in item
    assert "totalRuns" in item
