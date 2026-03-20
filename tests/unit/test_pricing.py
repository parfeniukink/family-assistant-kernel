from src.domain.analytics.pricing import estimate_pipeline_cost
from src.infrastructure.agents import AGENT_MODELS


def test_estimate_cost_orchestrator():
    stats = [{"agent": "orchestrator", "calls": 1, "errors": 0}]
    cost = estimate_pipeline_cost(stats, AGENT_MODELS)
    # orchestrator: 1 * (3000 * 0.40 + 1500 * 1.60) / 1_000_000
    #             = 1 * (1200 + 2400) / 1_000_000
    #             = 3600 / 1_000_000 = 0.0036
    assert round(cost, 5) == 0.0036


def test_estimate_cost_multiple_agents():
    stats = [
        {"agent": "orchestrator", "calls": 1, "errors": 0},
        {"agent": "microscope", "calls": 2, "errors": 0},
        {"agent": "telescope", "calls": 1, "errors": 0},
    ]
    cost = estimate_pipeline_cost(stats, AGENT_MODELS)
    assert cost > 0


def test_estimate_cost_unknown_agent():
    stats = [{"agent": "unknown_future_agent", "calls": 1, "errors": 0}]
    cost = estimate_pipeline_cost(stats, AGENT_MODELS)
    assert cost == 0.0


def test_estimate_cost_empty():
    assert estimate_pipeline_cost([], AGENT_MODELS) == 0.0
