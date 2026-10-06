from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

from app.config import Settings
from app.graph.llm import (
    FakeMealModel,
    _invoke_json_schema,
    _json_text,
    _schema_for_host,
    get_llm,
    llm_mode,
)
from app.schemas.chat import DraftChatPlan
from app.schemas.quick_add import DraftPantrySentence


def test_llm_mode_stays_fake_when_provider_is_fake() -> None:
    cfg = Settings(llm_provider="fake", openai_api_key="nvapi-test")
    assert llm_mode(cfg) == "fake"
    assert isinstance(get_llm(cfg), FakeMealModel)


def test_get_llm_passes_openai_compatible_base_url() -> None:
    cfg = Settings(
        llm_provider="real",
        llm_model="openai:z-ai/glm-5.3-flash",
        llm_base_url="https://integrate.api.nvidia.com/v1",
        llm_timeout=45,
        llm_max_tokens=2048,
        llm_max_retries=1,
        llm_temperature=1,
        llm_top_p=0.95,
        llm_thinking=True,
        openai_api_key="nvapi-test",
    )
    sentinel = MagicMock()
    with patch("app.graph.llm._init_chat_model", return_value=sentinel) as init:
        assert get_llm(cfg) is sentinel
    init.assert_called_once_with(
        "openai:z-ai/glm-5.3-flash",
        temperature=1.0,
        timeout=45.0,
        max_retries=1,
        max_tokens=2048,
        base_url="https://integrate.api.nvidia.com/v1",
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
        top_p=0.95,
    )


def test_json_text_strips_a_markdown_fence() -> None:
    raw = 'Sure.\n```json\n{"reply": "Keep them cold.", "actions": []}\n```'
    assert _json_text(raw).startswith("{")
    assert "```" not in _json_text(raw)


def test_hosted_schema_drops_the_decimal_lookahead() -> None:
    encoded = str(_schema_for_host(DraftPantrySentence))
    assert "(?!" not in encoded


def test_json_schema_invoke_rewrites_prose() -> None:
    class Host:
        def __init__(self) -> None:
            self.calls = 0

        def invoke(self, messages: object, **kwargs: object) -> AIMessage:
            assert kwargs["response_format"]["type"] == "json_schema"  # type: ignore[index]
            self.calls += 1
            del messages
            if self.calls == 1:
                return AIMessage(content="Keep leeks in the fridge.")
            return AIMessage(content='{"reply": "Keep leeks in the fridge.", "actions": []}')

    plan = _invoke_json_schema(Host(), DraftChatPlan, [])  # type: ignore[arg-type]
    assert plan.reply.startswith("Keep leeks")
    assert plan.actions == []


def test_json_schema_invoke_parses_a_fenced_plan() -> None:
    class Host:
        def invoke(self, messages: object, **kwargs: object) -> AIMessage:
            assert kwargs["response_format"]["type"] == "json_schema"  # type: ignore[index]
            del messages
            return AIMessage(
                content='```json\n{"reply": "Keep leeks in the fridge.", "actions": []}\n```'
            )

    plan = _invoke_json_schema(Host(), DraftChatPlan, [])  # type: ignore[arg-type]
    assert plan.reply.startswith("Keep leeks")
    assert plan.actions == []
