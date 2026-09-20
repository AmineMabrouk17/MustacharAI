"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from mustachar.api.ratelimit import RateLimitMiddleware
from mustachar.api.websocket import router as ws_router
from mustachar.core.settings import settings
from mustachar.pipeline.orchestrator import run_pipeline


class AskRequest(BaseModel):
    """Payload for the ``/api/v1/ask`` endpoint."""

    question: str = Field(..., min_length=1, max_length=5000)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RateLimitMiddleware)

    app.include_router(ws_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    @app.post("/api/v1/ask")
    async def ask(body: AskRequest) -> dict[str, object]:
        result = await run_pipeline(body.question)
        return {
            "question": result.question,
            "reformulated_query": result.reformulated_query,
            "answer": result.answer,
            "citations": result.citations,
            "fallback": result.fallback,
            "stage_latencies_ms": result.stage_latencies_ms,
            "total_latency_ms": result.total_latency_ms,
        }

    return app


app = create_app()
