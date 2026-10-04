from unittest.mock import MagicMock, patch

from app.config import Settings
from app.graph.llm import FakeMealModel, get_llm, llm_mode


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
        openai_api_key="nvapi-test",
    )
    sentinel = MagicMock()
    with patch("app.graph.llm._init_chat_model", return_value=sentinel) as init:
        assert get_llm(cfg) is sentinel
    init.assert_called_once_with(
        "openai:z-ai/glm-5.3-flash",
        temperature=0,
        timeout=45.0,
        max_retries=1,
        max_tokens=2048,
        base_url="https://integrate.api.nvidia.com/v1",
    )
