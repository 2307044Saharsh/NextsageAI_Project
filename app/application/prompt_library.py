from pathlib import Path

from app.domain.models import ChatContext, ChatTurn, DiagnosisInput


class PromptLibrary:
    """Loads the reviewed prompt asset instead of duplicating prompts in provider code."""

    def __init__(self, diagnosis_path: str | Path, chat_path: str | Path):
        self.diagnosis_path = Path(diagnosis_path)
        self.chat_path = Path(chat_path)

    def render_diagnosis_prompt(self, case: DiagnosisInput) -> str:
        template = self.diagnosis_path.read_text(encoding="utf-8").strip()
        return f"{template}\n\n## Evidence-only case input\n{case.model_dump_json()}"

    def render_chat_prompt(self, message: str, history: list[ChatTurn], context: ChatContext | None) -> str:
        template = self.chat_path.read_text(encoding="utf-8").strip()
        history_block = "\n".join(f"{turn.role}: {turn.content}" for turn in history[-8:]) or "(no prior turns)"
        context_block = "None"
        if context and context.case_evidence:
            context_block = (
                f"case_id={context.case_id}\n"
                f"title={context.case_title}\n"
                f"evidence:\n{context.case_evidence}"
            )
        return (
            f"{template}\n\n"
            f"## Optional lab context\n{context_block}\n\n"
            f"## Conversation so far\n{history_block}\n\n"
            f"## Latest human message\n{message}"
        )
