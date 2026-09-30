import json

from app.application.prompt_library import PromptLibrary
from app.domain.models import ChatContext, ChatResponse, ChatTurn, Diagnosis, DiagnosisInput
from app.infrastructure.fallback_provider import FallbackDiagnosisProvider
from app.infrastructure.llm_client import LiveModelClient, evidence_supported


DIAGNOSIS_SYSTEM = (
    "You are Sage, a cautious Cisco Packet Tracer troubleshooting assistant. "
    "Return valid JSON only with keys: root_cause, osi_layer, confidence, evidence, "
    "next_command, fix_steps, alternative_hypotheses, verification_command, "
    "verification_expected_result, safety_note. Never invent show-command output."
)

CHAT_SYSTEM = (
    "You are Sage, a patient Cisco lab mentor. Return valid JSON only with keys: "
    "reply, reasoning, likely_layers, suggested_commands, follow_up_questions, safety_note."
)


def _source_for_backend(backend: str) -> str:
    if backend == "huggingface":
        return "huggingface"
    if backend == "ollama":
        return "ollama"
    return "fallback"


class LiveDiagnosisProvider:
    def __init__(self, llm: LiveModelClient, fallback: FallbackDiagnosisProvider, prompts: PromptLibrary):
        self.llm = llm
        self.fallback = fallback
        self.prompts = prompts
        self.checker = fallback.checker

    def diagnose(self, case: DiagnosisInput) -> Diagnosis:
        try:
            user_prompt = self.prompts.render_diagnosis_prompt(case)
            payload, backend = self.llm.complete_json(DIAGNOSIS_SYSTEM, user_prompt)
            payload.pop("source", None)
            diagnosis = Diagnosis.model_validate({**payload, "source": "fallback"})
            if not evidence_supported(diagnosis.evidence, case.evidence_text):
                return self.fallback.diagnose(case)
            return diagnosis.model_copy(update={"source": _source_for_backend(backend)})
        except Exception:
            return self.fallback.diagnose(case)


class LiveChatProvider:
    def __init__(self, llm: LiveModelClient, fallback, prompts: PromptLibrary):
        self.llm = llm
        self.fallback = fallback
        self.prompts = prompts

    def chat(self, message: str, history: list[ChatTurn], context: ChatContext | None = None) -> ChatResponse:
        try:
            user_prompt = self.prompts.render_chat_prompt(message, history, context)
            payload, backend = self.llm.complete_json(CHAT_SYSTEM, user_prompt, max_tokens=900)
            payload.pop("source", None)
            parsed = ChatResponse.model_validate({**payload, "source": "fallback"})
            return parsed.model_copy(
                update={
                    "source": _source_for_backend(backend),
                    "case_context_used": bool(context and context.case_evidence),
                }
            )
        except Exception:
            return self.fallback.chat(message, history, context)
