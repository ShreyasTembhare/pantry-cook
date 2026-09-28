from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.llm import MealProposal, Violation


class CookStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentence: str = Field(min_length=3, max_length=500)
    defer: bool = False

    @field_validator("sentence")
    @classmethod
    def sentence_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 3:
            raise ValueError("Sentence must be at least 3 characters")
        if len(stripped) > 500:
            raise ValueError("Sentence must be at most 500 characters")
        return stripped


class CookReviseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str = Field(min_length=1, max_length=300)
    defer: bool = False

    @field_validator("note")
    @classmethod
    def note_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Note must not be blank")
        if len(stripped) > 300:
            raise ValueError("Note must be at most 300 characters")
        return stripped


class CookConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_etag: str = Field(min_length=64, max_length=64)


class ResumePayload(BaseModel):
    """Value passed to ``Command(resume=...)`` after the confirm interrupt."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["confirm", "revise", "abandon"]
    note: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def revise_needs_note(self) -> ResumePayload:
        if self.note is not None:
            self.note = self.note.strip()
        if self.decision == "revise" and not self.note:
            raise ValueError("A note is required to revise")
        return self


class CookSessionRead(BaseModel):
    id: str
    status: Literal["running", "awaiting_user", "committed", "abandoned", "failed"]
    sentence: str
    attempt_count: int
    proposal: MealProposal | None = None
    proposal_etag: str | None = None
    violations: list[Violation] = Field(default_factory=list)
    meal_id: str | None = None
    error: dict[str, Any] | None = None
    created_at: str
    updated_at: str
    expires_at: str
