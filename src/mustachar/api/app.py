"""FastAPI application factory with dynamic document ingestion."""

from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from mustachar.api.ratelimit import RateLimitMiddleware
from mustachar.api.websocket import router as ws_router
from mustachar.core.settings import settings
from mustachar.pipeline.ingestion import ingest_file_bytes, list_indexed_documents
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
