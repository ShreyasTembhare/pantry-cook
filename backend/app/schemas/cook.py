from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.schemas.llm import MealProposal, Violation

AttemptTrigger = Literal["initial", "auto_repair", "user_revision"]


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
    acknowledge_expired: bool = False


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


class ProposalAttemptRead(BaseModel):
    """One proposal already stored on the cook graph, in checkpoint order."""

    model_config = ConfigDict(extra="ignore")

    attempt_no: int = Field(ge=1)
    trigger: AttemptTrigger
    user_note: str | None = None
    proposal: MealProposal | None = None


class CookSessionRead(BaseModel):
    id: str
    status: Literal["running", "awaiting_user", "committed", "abandoned", "failed"]
    sentence: str
    attempt_count: int
    proposal: MealProposal | None = None
    proposal_etag: str | None = None
    violations: list[Violation] = Field(default_factory=list)
    attempts: list[ProposalAttemptRead] = Field(default_factory=list)
    meal_id: str | None = None
    error: dict[str, Any] | None = None
    created_at: str
    updated_at: str
    expires_at: str


class CookSessionSummary(BaseModel):
    """Index row for the unfinished-proposal pill. The full proposal stays on GET by id."""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: Literal["running", "awaiting_user", "committed", "abandoned", "failed"]
    sentence: str
    attempt_count: int
    updated_at: str


def read_proposal_attempts(values: dict[str, Any]) -> list[ProposalAttemptRead]:
    """Read ``attempts`` from graph state. Junk rows are dropped, not fatal."""
    raw_attempts = values.get("attempts")
    if not isinstance(raw_attempts, list):
        return []
    parsed: list[ProposalAttemptRead] = []
    for index, item in enumerate(raw_attempts, start=1):
        if not isinstance(item, dict):
            continue
        note = item.get("user_note")
        user_note = note.strip() if isinstance(note, str) else None
        if not user_note:
            user_note = None
        raw_no = item.get("attempt_no")
        attempt_no = (
            raw_no
            if isinstance(raw_no, int) and not isinstance(raw_no, bool) and raw_no >= 1
            else index
        )
        parsed.append(
            ProposalAttemptRead(
                attempt_no=attempt_no,
                trigger=_attempt_trigger(item.get("trigger")),
                user_note=user_note,
                proposal=_proposal_or_none(item.get("proposal")),
            )
        )
    return parsed


def _attempt_trigger(value: Any) -> AttemptTrigger:
    if value == "auto_repair":
        return "auto_repair"
    if value == "user_revision":
        return "user_revision"
    return "initial"


def _proposal_or_none(raw: Any) -> MealProposal | None:
    if not isinstance(raw, dict) or not raw:
        return None
    try:
        return MealProposal.model_validate(raw)
    except ValidationError:
        return None
