"""Signal weight definitions for preference learning."""

from typing import Literal

NewsReaction = Literal["🔥", "👀", "😐", "👎"]

SIGNAL_WEIGHTS: dict[str, int] = {
    "🔥": 10,
    "👎": -10,
    "deleted": -15,
    "gc_deleted": -3,
    "bookmark": 5,
    "human_feedback": 8,
    "👀": 1,
    "😐": -1,
}
