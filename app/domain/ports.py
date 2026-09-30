from typing import Protocol

from app.domain.models import Case, ChatContext, ChatResponse, ChatTurn, Diagnosis, DiagnosisInput, Review


class CaseRepository(Protocol):
    def list_cases(self) -> list[Case]: ...
    def get_case(self, case_id: str) -> Case | None: ...


class ReviewRepository(Protocol):
    def list_reviews(self) -> list[Review]: ...
    def save_review(self, review: Review) -> Review: ...


class DiagnosisProvider(Protocol):
    def diagnose(self, case: DiagnosisInput) -> Diagnosis: ...


class ChatProvider(Protocol):
    def chat(self, message: str, history: list[ChatTurn], context: ChatContext | None = None) -> ChatResponse: ...
