"""Hardcoded OpenAI pricing for pipeline cost estimation."""

# $/1M tokens (as of March 2026)
MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "o4-mini": {"input": 1.10, "output": 4.40},
}

# Estimated tokens per call
AGENT_TOKEN_ESTIMATES: dict[str, dict[str, int]] = {
    "orchestrator": {"input": 3000, "output": 1500},
    "save": {"input": 0, "output": 0},
    "merge": {"input": 0, "output": 0},
    "preference": {"input": 2500, "output": 300},
    "microscope": {"input": 770, "output": 800},
    "telescope": {"input": 770, "output": 800},
}


def estimate_pipeline_cost(
    agent_stats: list[dict],
    agent_models: dict[str, str],
) -> float:
    """Estimate USD cost from per-agent call counts."""

    total = 0.0

    for stat in agent_stats:
        agent = stat["agent"]
        calls = stat["calls"]

        tokens = AGENT_TOKEN_ESTIMATES.get(agent)
        if tokens is None:
            continue

        model_name = agent_models.get(agent)
        if model_name is None:
            continue

        pricing = MODEL_PRICING.get(model_name)
        if pricing is None:
            continue

        cost = (
            calls
            * (
                tokens["input"] * pricing["input"]
                + tokens["output"] * pricing["output"]
            )
            / 1_000_000
        )

        total += cost

    return total
