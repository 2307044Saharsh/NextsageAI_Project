from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.application.fallback_chat import FallbackChatProvider
from app.application.prompt_library import PromptLibrary
from app.application.rules import CiscoRuleChecker
from app.application.service import TroubleshootingService
from app.config import Settings, get_settings
from app.infrastructure.fallback_provider import FallbackDiagnosisProvider
from app.infrastructure.file_repositories import CsvCaseRepository, CsvResponsibleAiLog, JsonReviewRepository
from app.infrastructure.live_providers import LiveChatProvider, LiveDiagnosisProvider
from app.infrastructure.llm_client import LiveModelClient
from app.mcp_server import mcp

base_dir = Path(__file__).resolve().parent.parent


def build_service(settings: Settings) -> TroubleshootingService:
    checker = CiscoRuleChecker()
    fallback = FallbackDiagnosisProvider(checker)
    prompts = PromptLibrary(
        base_dir / settings.prompt_file,
        base_dir / settings.chat_prompt_file,
    )
    llm = LiveModelClient(settings)
    provider = LiveDiagnosisProvider(llm, fallback, prompts)
    chat_provider = LiveChatProvider(llm, FallbackChatProvider(), prompts)
    service = TroubleshootingService(
        CsvCaseRepository(str(base_dir / settings.data_dir / "cases.csv")),
        JsonReviewRepository(str(base_dir / settings.data_dir / "reviews.json")),
        provider,
        chat_provider,
        CsvResponsibleAiLog(str(base_dir / settings.data_dir / "responsible_ai_log.csv")),
    )
    service.llm = llm
    return service


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    async with mcp.session_manager.run():
        yield


def create_app(settings: Settings | None = None, service: TroubleshootingService | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="NetSage AI",
        description="Human-reviewed network troubleshooting assistant",
        lifespan=lifespan,
    )
    app.state.service = service or build_service(settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Last-Event-ID", "Mcp-Method", "Mcp-Name", "Mcp-Protocol-Version", "Mcp-Session-Id"],
        expose_headers=["Mcp-Session-Id"],
    )
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=base_dir / "static"), name="static")
    app.mount("/mcp", mcp.streamable_http_app(streamable_http_path="/"))

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(base_dir / "static" / "index.html")

    return app


app = create_app()
