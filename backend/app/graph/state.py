from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

MAX_AUTO_REPAIR = 3
MAX_TOTAL_ATTEMPTS = 8


class CookState(TypedDict):
    session_id: str
    sentence: str
    pantry_snapshot: list[dict[str, Any]]
    constraints: dict[str, Any] | None
    proposal: dict[str, Any] | None
    violations: list[dict[str, Any]]
    attempts: Annotated[list[dict[str, Any]], operator.add]
    user_notes: Annotated[list[str], operator.add]
    decision: str | None
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    repair_used: int
    next_trigger: str


def initial_cook_state(session_id: str, sentence: str) -> CookState:
    return {
        "session_id": session_id,
        "sentence": sentence,
        "pantry_snapshot": [],
        "constraints": None,
        "proposal": None,
        "violations": [],
        "attempts": [],
        "user_notes": [],
        "decision": None,
        "result": None,
        "error": None,
        "repair_used": 0,
        "next_trigger": "initial",
    }
