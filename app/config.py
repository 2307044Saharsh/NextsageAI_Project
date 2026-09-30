from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    hf_api_token: str | None = None
    hf_model: str = "meta-llama/Llama-3.2-3B-Instruct"
    hf_router_url: str = "https://router.huggingface.co/v1"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:latest"
    ai_backend: str = "auto"  # auto | huggingface | ollama | fallback
    llm_timeout_seconds: int = 90
    allowed_origins: str = "http://localhost:8000"
    data_dir: str = "data"
    prompt_file: str = "prompts/diagnose_prompt.md"
    chat_prompt_file: str = "prompts/chat_prompt.md"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
