from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "PANTRY_", "env_file": ".env"}

    db_path: Path = Path("data/pantry.sqlite")
    checkpoint_db_path: Path = Path("data/checkpoints.sqlite")

    llm_provider: str = "fake"
    llm_model: str = "openai:gpt-4o-mini"
    openai_api_key: str = ""

    host: str = "0.0.0.0"
    port: int = 8787

    cors_origins: list[str] = [
        "http://localhost:3939",
        "http://127.0.0.1:3939",
    ]


settings = Settings()
