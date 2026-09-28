from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.graph.edges import (
    route_after_parse,
    route_after_propose,
    route_after_user,
    route_after_validate,
)
from app.graph.nodes import (
    await_user,
    commit_meal,
    fail,
    load_pantry,
    parse_sentence,
    propose_meal,
    validate_proposal,
)
from app.graph.state import CookState

SessionFactory = Callable[[], Session]


def build_graph(
    checkpointer: Any,
    llm: BaseChatModel,
    session_factory: SessionFactory,
) -> Any:
    """Compile the cook graph.

    ``llm`` and ``session_factory`` are closed over here so the checkpoint
    config only carries the serialisable ``thread_id``.
    """

    def _load(state: CookState) -> dict[str, Any]:
        return load_pantry(state, session_factory)

    def _parse(state: CookState) -> dict[str, Any]:
        return parse_sentence(state, llm)

    def _propose(state: CookState) -> dict[str, Any]:
        return propose_meal(state, llm)

    def _commit(state: CookState) -> dict[str, Any]:
        return commit_meal(state, session_factory)

    graph: StateGraph[CookState] = StateGraph(CookState)
    graph.add_node("load_pantry", _load)
    graph.add_node("parse_sentence", _parse)
    graph.add_node("propose_meal", _propose)
    graph.add_node("validate_proposal", validate_proposal)
    graph.add_node("await_user", await_user)
    graph.add_node("commit_meal", _commit)
    graph.add_node("fail", fail)

    graph.add_edge(START, "load_pantry")
    graph.add_edge("load_pantry", "parse_sentence")
    graph.add_conditional_edges(
        "parse_sentence",
        route_after_parse,
        {"propose_meal": "propose_meal", "fail": "fail"},
    )
    graph.add_conditional_edges(
        "propose_meal",
        route_after_propose,
        {"validate_proposal": "validate_proposal", "fail": "fail"},
    )
    graph.add_conditional_edges(
        "validate_proposal",
        route_after_validate,
        {
            "propose_meal": "propose_meal",
            "await_user": "await_user",
            "fail": "fail",
        },
    )
    graph.add_conditional_edges(
        "await_user",
        route_after_user,
        {
            "commit_meal": "commit_meal",
            "propose_meal": "propose_meal",
            "abandon": END,
            "fail": "fail",
        },
    )
    graph.add_edge("commit_meal", END)
    graph.add_edge("fail", END)
    return graph.compile(checkpointer=checkpointer)
