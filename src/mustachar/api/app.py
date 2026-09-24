"""FastAPI application factory with dynamic document ingestion."""

from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from mustachar.api.ratelimit import RateLimitMiddleware
from mustachar.api.websocket import router as ws_router
from mustachar.core.settings import settings
from mustachar.infra import llm_client
from mustachar.pipeline.ingestion import (
    delete_source,
    ingest_file_bytes,
    list_indexed_documents,
)
from mustachar.pipeline.orchestrator import run_pipeline


class AskRequest(BaseModel):
    """Payload for the ``/api/v1/ask`` endpoint."""

    question: str = Field(..., min_length=1, max_length=5000)


class ModelRequest(BaseModel):
    """Payload for switching the active LLM (`POST /api/v1/models/active`)."""

    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)


class OpenRouterConfigRequest(BaseModel):
    """Payload for registering a user-provided OpenRouter key + model."""

    api_key: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)


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

    @app.get("/api/v1/documents")
    async def get_documents() -> list[dict[str, Any]]:
        """Return list of legal documents currently indexed."""
        return list_indexed_documents()

    @app.post("/api/v1/documents/upload")
    async def upload_document(file: UploadFile = File(...)) -> dict[str, Any]:  # noqa: B008
        """Upload and index a legal PDF or TXT file into ChromaDB."""
        allowed_extensions = {".pdf", ".txt"}
        filename = file.filename or "unknown.txt"

        if not any(filename.lower().endswith(ext) for ext in allowed_extensions):
            raise HTTPException(
                status_code=400,
                detail="نوع الملف غير مدعوم. يرجى رفع ملف بصيغة PDF أو TXT فقط.",
            )

        try:
            content = await file.read()
            result = ingest_file_bytes(content, filename)
            return result
        except ValueError as val_err:
            raise HTTPException(status_code=422, detail=str(val_err)) from None
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"حدث خطأ أثناء فهرسة الملف: {exc}",
            ) from None

    @app.get("/api/v1/models")
    async def get_models() -> dict[str, Any]:
        """List available LLM providers/models and the active model."""
        return {
            "providers": [
                {"id": pid, "label": p["label"], "models": p["models"]}
                for pid, p in llm_client.PROVIDERS.items()
            ],
            "active": llm_client.get_active_model(),
            "openrouter_configured": bool(
                llm_client.get_openrouter_config().get("api_key")
            ),
        }

    @app.post("/api/v1/models/openrouter")
    async def configure_openrouter(
        body: OpenRouterConfigRequest,
    ) -> dict[str, Any]:
        """Register a user-provided OpenRouter API key and model name.

        The key is validated against OpenRouter's ``/auth/key`` endpoint before
        the config is persisted (survives server restarts).
        """
        if not await llm_client.validate_openrouter_key(body.api_key):
            raise HTTPException(
                status_code=400,
                detail=(
                    "مفتاح OpenRouter غير صالح أو تعذّر التحقق منه. "
                    "تحقق من المفتاح (sk-or-v1-...) ثم أعد المحاولة."
                ),
            )
        try:
            cfg = llm_client.set_openrouter_config(body.api_key, body.model)
        except ValueError as val_err:
            raise HTTPException(status_code=422, detail=str(val_err)) from None
        return {
            "configured": True,
            "model": cfg["model"],
            "providers": [
                {"id": pid, "label": p["label"], "models": p["models"]}
                for pid, p in llm_client.PROVIDERS.items()
            ],
        }

    @app.post("/api/v1/models/active")
    async def set_models_active(body: ModelRequest) -> dict[str, Any]:
        """Switch the LLM used for generation/reformulation."""
        try:
            return {"active": llm_client.set_active_model(body.provider, body.model)}
        except ValueError as val_err:
            raise HTTPException(status_code=422, detail=str(val_err)) from None

    @app.delete("/api/v1/documents/{source}")
    async def delete_document(source: str) -> dict[str, Any]:
        """Delete every chunk of one indexed document (matched by source name)."""
        removed = delete_source(source)
        if removed == 0:
            raise HTTPException(
                status_code=404,
                detail=f"المصدر «{source}» غير موجود في القوانين المفهرسة.",
            )
        return {"source": source, "removed_chunks": removed}

    @app.post("/api/v1/ask")
    async def ask(body: AskRequest) -> dict[str, object]:
        result = await run_pipeline(body.question)
        return {
            "question": result.question,
            "reformulated_query": result.reformulated_query,
            "answer": result.answer,
            "citations": result.citations,
            "fallback": result.fallback,
            "error": result.error,
            "stage_latencies_ms": result.stage_latencies_ms,
            "total_latency_ms": result.total_latency_ms,
        }

    return app


app = create_app()
