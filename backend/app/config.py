from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PANTRY_",
        env_file=_ENV_FILE,
        extra="ignore",
        populate_by_name=True,
    )

    database_url: str = "postgresql+psycopg://pantry:pantry@localhost:5432/pantry"

    llm_provider: str = "fake"
    llm_model: str = "openai:gpt-4o-mini"
    llm_base_url: str = ""
    llm_timeout: float = 30
    llm_max_tokens: int = 0
    llm_max_retries: int = 2
    # The provider client reads this name. It is not PANTRY_OPENAI_API_KEY.
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")

    env: str = "development"
    maintenance: bool = True

    cors_origins: list[str] = [
        "http://localhost:3939",
        "http://127.0.0.1:3939",
    ]

    @field_validator("maintenance", mode="before")
    @classmethod
    def parse_maintenance(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower() not in {"0", "false", "off", "no"}
        return value


settings = Settings()
