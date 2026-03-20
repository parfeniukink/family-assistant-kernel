"""Preference learning agent.

Analyzes user reactions to news articles and builds structured
filtering rules. No sub-agents — works directly.
"""

from dataclasses import dataclass

from pydantic_ai import Agent, RunContext

from src import domain
from src.domain.news import PreferenceRules
from src.infrastructure.agents import AGENT_MODELS, get_model

# ── Deps ──


@dataclass
class PreferenceContext:
    reactions: list[dict]  # [{title, reaction, bookmarked, feedback}]
    filter_prompt: str = ""
    existing_skip: list[str] = None  # type: ignore[assignment]
    existing_high_priority: list[str] = None  # type: ignore[assignment]
    existing_recently_deleted: list[dict] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.existing_skip is None:
            self.existing_skip = []
        if self.existing_high_priority is None:
            self.existing_high_priority = []
        if self.existing_recently_deleted is None:
            self.existing_recently_deleted = []


# ── Agent ──

preference_agent = Agent(
    get_model(AGENT_MODELS["preference"]),
    deps_type=PreferenceContext,
    output_type=PreferenceRules,
)


@preference_agent.system_prompt
async def _preference_prompt(ctx: RunContext[PreferenceContext]) -> str:
    lines = []
    for r in ctx.deps.reactions:
        parts = [
            f"- \"{r.get('title', '?')}\":",
            f"reaction={r.get('reaction', 'none')}",
            f"bookmarked={r.get('bookmarked', False)}",
            f"feedback={r.get('feedback', 'none')}",
            f"weight={r.get('weight', 0)}",
        ]
        if r.get("deleted"):
            parts.append("DELETED")
        lines.append(" ".join(parts))
    reactions_text = chr(10).join(lines) or "No reactions yet."

    existing_skip = (
        chr(10).join(f"- {s}" for s in ctx.deps.existing_skip) or "None."
    )
    existing_high_priority = (
        chr(10).join(f"- {b}" for b in ctx.deps.existing_high_priority)
        or "None."
    )

    if ctx.deps.existing_recently_deleted:
        deleted_lines = []
        for d in ctx.deps.existing_recently_deleted:
            line = f"- \"{d['title']}\""
            if d.get("deleted_at"):
                line += f" (deleted: {d['deleted_at']})"
            if d.get("feedback"):
                line += f" — \"{d['feedback']}\""
            deleted_lines.append(line)
        existing_recently_deleted = chr(10).join(deleted_lines)
    else:
        existing_recently_deleted = "None."

    filter_prompt = ctx.deps.filter_prompt or "No specific filter."

    return domain.prompts.SYSTEM_PREFERENCE.format(
        reactions=reactions_text,
        existing_skip=existing_skip,
        existing_high_priority=existing_high_priority,
        existing_recently_deleted=existing_recently_deleted,
        filter_prompt=filter_prompt,
    )
