import json

import httpx

from app.application.prompt_library import PromptLibrary
from app.config import Settings
from app.domain.models import Diagnosis, DiagnosisInput
from app.domain.ports import DiagnosisProvider


class HuggingFaceDiagnosisProvider(DiagnosisProvider):
    def __init__(self, settings: Settings, fallback: DiagnosisProvider, prompts: PromptLibrary):
        self.settings = settings
        self.fallback = fallback
        self.prompts = prompts
        self.checker = getattr(fallback, "checker", None)

    def diagnose(self, case: DiagnosisInput) -> Diagnosis:
        if not self.settings.hf_api_token:
            return self.fallback.diagnose(case)
        prompt = self.prompts.render_diagnosis_prompt(case)
        try:
            response = httpx.post(
                f"https://api-inference.huggingface.co/models/{self.settings.hf_model}",
                headers={"Authorization": f"Bearer {self.settings.hf_api_token}"},
                json={"inputs": prompt, "parameters": {"max_new_tokens": 500, "return_full_text": False}},
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            text = payload[0]["generated_text"] if isinstance(payload, list) else payload["generated_text"]
            start, end = text.find("{"), text.rfind("}")
            diagnosis = Diagnosis.model_validate(json.loads(text[start:end + 1]))
            if any(item not in case.evidence_text for item in diagnosis.evidence):
                return self.fallback.diagnose(case)
            return diagnosis.model_copy(update={"source": "huggingface"})
        except (httpx.HTTPError, KeyError, ValueError, IndexError, json.JSONDecodeError):
            return self.fallback.diagnose(case)
