"""FastAPI application factory."""

from fastapi import FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from mustachar.api.websocket import router as ws_router
from mustachar.core.settings import settings
from mustachar.pipeline.orchestrator import run_pipeline
from mustachar.pipeline.tts import tts_full


class SpeakRequest(BaseModel):
    """Payload for the ``/api/v1/speak`` endpoint."""

    text: str = Field(..., min_length=1, max_length=5000)
    voice: str = Field(default="ar-TN-HediNeural")


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

    app.include_router(ws_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    @app.post("/api/v1/ask")
    async def ask(audio: UploadFile) -> dict[str, object]:
        audio_bytes = await audio.read()
        result = await run_pipeline(audio_bytes, audio.filename or "audio.webm")
        return {
            "transcript": result.transcript,
            "reformulated_query": result.reformulated_query,
            "answer": result.answer,
            "citations": result.citations,
            "fallback": result.fallback,
            "stage_latencies_ms": result.stage_latencies_ms,
            "total_latency_ms": result.total_latency_ms,
        }

    @app.post("/api/v1/speak")
    async def speak(body: SpeakRequest) -> Response:
        audio = await tts_full(body.text, voice=body.voice)
        return Response(content=audio, media_type="audio/mpeg")

    return app


app = create_app()
