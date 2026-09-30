from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


ReviewStatus = Literal["Pending", "Accepted", "Edited", "Rejected"]


class Case(BaseModel):
    case_id: str
    title: str
    symptom: str
    topology_note: str
    show_outputs: str
    expected_fault: str
    osi_layer: str
    concept: str
    severity: Literal["Low", "Medium", "High", "Critical"]

    def diagnosis_input(self) -> "DiagnosisInput":
        """Return only the evidence that a diagnostic system is allowed to see."""
        return DiagnosisInput(
            case_id=self.case_id,
            title=self.title,
            symptom=self.symptom,
            topology_note=self.topology_note,
            show_outputs=self.show_outputs,
        )


class DiagnosisInput(BaseModel):
    """Evidence-only representation of a case; intentionally excludes answer-key fields."""

    case_id: str
    title: str
    symptom: str
    topology_note: str
    show_outputs: str

    @property
    def evidence_text(self) -> str:
        return "\n".join((self.symptom, self.topology_note, self.show_outputs))


class EvidenceFinding(BaseModel):
    rule: str
    severity: Literal["Low", "Medium", "High", "Critical"]
    root_cause: str
    osi_layer: str
    confidence: Literal["low", "medium", "high"]
    evidence: str
    next_command: str
    fix_steps: list[str]
    verification_command: str
    verification_expected_result: str


class Diagnosis(BaseModel):
    root_cause: str
    osi_layer: str
    confidence: Literal["low", "medium", "high"]
    evidence: list[str] = Field(min_length=1)
    next_command: str
    fix_steps: list[str] = Field(min_length=1)
    alternative_hypotheses: list[str] = Field(default_factory=list, max_length=3)
    verification_command: str
    verification_expected_result: str
    safety_note: str = "A human reviewer must validate this recommendation before applying changes."
    source: Literal["rules", "huggingface", "fallback", "ollama"]


class Review(BaseModel):
    review_id: str = Field(default_factory=lambda: str(uuid4()))
    case_id: str
    status: ReviewStatus
    reviewer_name: str = Field(min_length=1, max_length=80)
    corrected_diagnosis: str | None = Field(default=None, max_length=2000)
    reason: str | None = Field(default=None, max_length=2000)
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    diagnosis_snapshot: Diagnosis | None = None


class DiagnoseRequest(BaseModel):
    case_id: str


class ReviewRequest(BaseModel):
    status: ReviewStatus
    reviewer_name: str = Field(min_length=1, max_length=80)
    corrected_diagnosis: str | None = Field(default=None, max_length=2000)
    reason: str | None = Field(default=None, max_length=2000)


class DashboardSummary(BaseModel):
    total_cases: int
    reviewed_cases: int
    agreement_rate: float
    by_concept: dict[str, int]
    by_severity: dict[str, int]
    review_status: dict[str, int]
    responsible_ai_corrections: int = 0
    correction_status: dict[str, int] = Field(default_factory=dict)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatContext(BaseModel):
    case_id: str | None = None
    case_title: str | None = None
    case_evidence: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=24)
    case_id: str | None = None
    include_case_context: bool = True


class ChatResponse(BaseModel):
    reply: str
    reasoning: list[str] = Field(min_length=1)
    likely_layers: list[str] = Field(default_factory=list)
    suggested_commands: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    case_context_used: bool = False
    source: Literal["huggingface", "fallback", "rules", "ollama"] = "fallback"
    safety_note: str = "A human reviewer must validate this guidance before applying changes."
