import json
import re
from typing import Any

import httpx

from app.config import Settings


class LiveModelClient:
    """Calls live LLM backends (Hugging Face router, then Ollama) for JSON-shaped answers."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def status(self) -> dict[str, Any]:
        backends: list[dict[str, Any]] = []
        active = None

        if self.settings.hf_api_token:
            hf = self._probe_huggingface()
            backends.append(hf)
            if hf["available"] and self.settings.ai_backend in ("auto", "huggingface"):
                active = "huggingface"

        ollama = self._probe_ollama()
        backends.append(ollama)
        if ollama["available"] and active is None and self.settings.ai_backend in ("auto", "ollama"):
            active = "ollama"

        if self.settings.ai_backend == "fallback":
            active = None
        elif self.settings.ai_backend == "ollama":
            active = "ollama" if ollama["available"] else None
        elif self.settings.ai_backend == "huggingface":
            hf_backend = next((item for item in backends if item["name"] == "huggingface"), None)
            active = "huggingface" if hf_backend and hf_backend.get("available") else None

        return {
            "active_backend": active or "fallback",
            "configured_backend": self.settings.ai_backend,
            "backends": backends,
            "note": (
                "Live model active."
                if active
                else "Using deterministic rules fallback. Start Ollama or fix HF Inference Providers token permission."
            ),
        }

    def complete_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 700) -> tuple[dict[str, Any], str]:
        errors: list[str] = []
        order = self._backend_order()
        for backend in order:
            try:
                if backend == "huggingface":
                    text = self._complete_huggingface(system_prompt, user_prompt, max_tokens)
                elif backend == "ollama":
                    text = self._complete_ollama(system_prompt, user_prompt, max_tokens)
                else:
                    continue
                return self._parse_json(text), backend
            except Exception as error:  # noqa: BLE001 - collect and try next backend
                errors.append(f"{backend}: {error}")
        raise RuntimeError("; ".join(errors) or "No live model backend available")

    def _backend_order(self) -> list[str]:
        if self.settings.ai_backend == "huggingface":
            return ["huggingface"]
        if self.settings.ai_backend == "ollama":
            return ["ollama"]
        if self.settings.ai_backend == "fallback":
            return []
        return ["huggingface", "ollama"]

    def _probe_huggingface(self) -> dict[str, Any]:
        if not self.settings.hf_api_token:
            return {"name": "huggingface", "available": False, "detail": "HF_API_TOKEN not set"}
        try:
            response = httpx.post(
                f"{self.settings.hf_router_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.hf_api_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.settings.hf_model,
                    "messages": [{"role": "user", "content": "Reply JSON only: {\"ok\":true}"}],
                    "max_tokens": 20,
                    "temperature": 0,
                    "stream": False,
                },
                timeout=20,
            )
            if response.status_code == 403:
                raise RuntimeError(
                    "HF token lacks Inference Providers permission. Create a fine-grained token with "
                    "'Make calls to Inference Providers' at huggingface.co/settings/tokens"
                )
            response.raise_for_status()
            return {"name": "huggingface", "available": True, "model": self.settings.hf_model}
        except Exception as error:  # noqa: BLE001
            return {"name": "huggingface", "available": False, "detail": str(error)}

    def _probe_ollama(self) -> dict[str, Any]:
        try:
            response = httpx.get(
                f"{self.settings.ollama_base_url.rstrip('/')}/api/tags",
                timeout=5,
            )
            response.raise_for_status()
            models = [item.get("name") for item in response.json().get("models", [])]
            available = self.settings.ollama_model in models or any(
                self.settings.ollama_model.split(":")[0] in (name or "") for name in models
            )
            if not available and models:
                return {
                    "name": "ollama",
                    "available": False,
                    "detail": f"Model {self.settings.ollama_model} not pulled. Run: ollama pull {self.settings.ollama_model}",
                    "models": models,
                }
            return {"name": "ollama", "available": True, "model": self.settings.ollama_model, "models": models}
        except Exception as error:  # noqa: BLE001
            return {"name": "ollama", "available": False, "detail": str(error)}

    def _complete_huggingface(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        if not self.settings.hf_api_token:
            raise RuntimeError("HF_API_TOKEN not set")
        response = httpx.post(
            f"{self.settings.hf_router_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.settings.hf_api_token}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.hf_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.2,
                "stream": False,
            },
            timeout=self.settings.llm_timeout_seconds,
        )
        if response.status_code == 403:
            raise RuntimeError(
                "HF token lacks Inference Providers permission. Create a fine-grained token with "
                "'Make calls to Inference Providers' at huggingface.co/settings/tokens"
            )
        response.raise_for_status()
        payload = response.json()
        return payload["choices"][0]["message"]["content"]

    def _complete_ollama(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        response = httpx.post(
            f"{self.settings.ollama_base_url.rstrip('/')}/api/chat",
            json={
                "model": self.settings.ollama_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": max_tokens},
            },
            timeout=self.settings.llm_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("Model response did not contain JSON")
        return json.loads(text[start : end + 1])


def evidence_supported(evidence: list[str], case_text: str) -> bool:
    """Allow paraphrased evidence from live models, not only exact substrings."""
    haystack = case_text.lower()
    for item in evidence:
        keywords = [word for word in re.findall(r"[a-z0-9]{4,}", item.lower())]
        if not keywords:
            continue
        if sum(1 for word in keywords if word in haystack) >= max(1, len(keywords) // 3):
            return True
    return False
