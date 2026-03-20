"""Perception augmentation agents (microscope + telescope).

Sub-agents
----------
_microscope_agent – deep-dive technical analysis (reasoning)
_telescope_agent  – big-picture context analysis (reasoning)
"""

from dataclasses import dataclass

from pydantic_ai import Agent, RunContext

from src import domain
from src.domain.news import PreferenceRules
from src.infrastructure.agents import AGENT_MODELS, get_model

# ── Deps ──


@dataclass
class AnalysisContext:
    title: str
    description: str
    feedback_history: list[tuple[str, str]]
    preference_profile: str


def _format_interests(preference_profile: str) -> str:
    rules = PreferenceRules.from_stored(preference_profile)
    if rules.high_priority:
        return "\n".join(f"- {b}" for b in rules.high_priority)
    return "No profile yet."


# ── Sub-agents ──

# Microscope Agent (reasoning model)
microscope_agent = Agent(
    get_model(AGENT_MODELS["microscope"]),
    deps_type=AnalysisContext,
    output_type=str,
)


@microscope_agent.system_prompt
async def _microscope_prompt(
    ctx: RunContext[AnalysisContext],
) -> str:
    history = ""
    if ctx.deps.feedback_history:
        history = "\n".join(
            f'- "{t}": {fb}' for t, fb in ctx.deps.feedback_history[:20]
        )
    interests = _format_interests(ctx.deps.preference_profile)
    feedback = history or "No feedback yet."

    return domain.prompts.SYSTEM_MICROSCOPE.format(
        interests=interests,
        feedback=feedback,
    )


# Telescope Agent (reasoning model)
telescope_agent = Agent(
    get_model(AGENT_MODELS["telescope"]),
    deps_type=AnalysisContext,
    output_type=str,
)


@telescope_agent.system_prompt
async def _telescope_prompt(
    ctx: RunContext[AnalysisContext],
) -> str:
    history = ""
    if ctx.deps.feedback_history:
        history = "\n".join(
            f'- "{t}": {fb}' for t, fb in ctx.deps.feedback_history[:20]
        )
    interests = _format_interests(ctx.deps.preference_profile)
    feedback = history or "No feedback yet."

    return domain.prompts.SYSTEM_TELESCOPE.format(
        interests=interests,
        feedback=feedback,
    )
