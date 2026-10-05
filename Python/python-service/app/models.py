"""Pydantic models define and validate JSON request/response fields."""

from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Context(Model):
    """Trusted caller scope supplied by Spring Boot."""

    tenant: StrictStr
    role: StrictStr
    as_of: date


class Question(Context):
    question: StrictStr = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def nonblank(self):
        if not self.question.strip():
            raise ValueError("Question cannot be blank.")
        return self


class Policy(Model):
    """One source record from the policy PDF; effective_to is exclusive."""

    id: StrictStr
    tenant: StrictStr
    role: StrictStr
    approval_state: Literal["Approved", "Draft"]
    effective_from: date
    effective_to: date
    text: StrictStr

    @model_validator(mode="after")
    def interval(self):
        if self.effective_to <= self.effective_from or not self.text.strip():
            raise ValueError("Invalid policy interval or empty text.")
        return self


class Citation(Model):
    chunk_id: StrictStr
    quote: StrictStr


class Answer(Model):
    """The three supported policy outcomes, with exact source citations."""

    status: Literal["ANSWERED", "INSUFFICIENT_EVIDENCE", "CONFLICT"]
    answer: StrictStr | None
    citations: list[Citation]


class Extracted(Model):
    """Missing or ambiguous document fields remain null."""

    benefit: str | None
    amount: float | None = Field(allow_inf_nan=False)
    currency: str | None
    reference: str | None


class Analysis(Model):
    extracted: Extracted
    field_evidence: dict[str, list[str]]
    policy: Answer | None
    issues: list[str]
