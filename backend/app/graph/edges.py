from __future__ import annotations

from app.graph.state import CookState


def route_after_parse(state: CookState) -> str:
    if state.get("error"):
        return "fail"
    return "propose_meal"


def route_after_propose(state: CookState) -> str:
    if state.get("error") or not state.get("proposal"):
        return "fail"
    return "validate_proposal"


def route_after_validate(state: CookState) -> str:
    if state.get("error"):
        return "fail"
    if state.get("violations"):
        return "propose_meal"
    return "await_user"


def route_after_user(state: CookState) -> str:
    if state.get("error"):
        return "fail"
    decision = state.get("decision")
    if decision == "confirm":
        return "commit_meal"
    if decision == "revise":
        return "propose_meal"
    return "abandon"
