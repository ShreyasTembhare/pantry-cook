from pathlib import Path

from pydantic_settings import BaseSettings

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = {"env_prefix": "PANTRY_", "env_file": _ENV_FILE, "extra": "ignore"}

    database_url: str = "postgresql+psycopg://pantry:pantry@localhost:5432/pantry"

    llm_provider: str = "fake"
    llm_model: str = "openai:gpt-4o-mini"
    llm_base_url: str = ""
    llm_timeout: float = 30
    llm_max_tokens: int = 0
    llm_max_retries: int = 2
    openai_api_key: str = ""

    host: str = "0.0.0.0"
    port: int = 8787

    cors_origins: list[str] = [
        "http://localhost:3939",
        "http://127.0.0.1:3939",
    ]


settings = Settings()
