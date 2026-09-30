import json

import httpx

from app.application.fallback_chat import FallbackChatProvider
from app.application.prompt_library import PromptLibrary
from app.config import Settings
from app.domain.models import ChatContext, ChatResponse, ChatTurn


class HuggingFaceChatProvider:
    def __init__(self, settings: Settings, fallback: FallbackChatProvider, prompts: PromptLibrary):
        self.settings = settings
        self.fallback = fallback
        self.prompts = prompts

    def chat(self, message: str, history: list[ChatTurn], context: ChatContext | None = None) -> ChatResponse:
        if not self.settings.hf_api_token:
            return self.fallback.chat(message, history, context)

        prompt = self.prompts.render_chat_prompt(message, history, context)
        try:
            response = httpx.post(
                f"https://api-inference.huggingface.co/models/{self.settings.hf_model}",
                headers={"Authorization": f"Bearer {self.settings.hf_api_token}"},
                json={"inputs": prompt, "parameters": {"max_new_tokens": 700, "return_full_text": False}},
                timeout=45,
            )
            response.raise_for_status()
            payload = response.json()
            text = payload[0]["generated_text"] if isinstance(payload, list) else payload["generated_text"]
            start, end = text.find("{"), text.rfind("}")
            parsed = ChatResponse.model_validate(json.loads(text[start : end + 1]))
            return parsed.model_copy(
                update={
                    "source": "huggingface",
                    "case_context_used": bool(context and context.case_evidence),
                }
            )
        except (httpx.HTTPError, KeyError, ValueError, IndexError, json.JSONDecodeError):
            return self.fallback.chat(message, history, context)
