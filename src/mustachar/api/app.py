"""FastAPI application factory."""

from fastapi import FastAPI, UploadFile

from mustachar.core.settings import settings
from mustachar.pipeline.stt import speech_to_text


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    @app.post("/api/v1/ask")
    async def ask(audio: UploadFile) -> dict[str, str]:
        audio_bytes = await audio.read()
        transcript = await speech_to_text(audio_bytes, audio.filename or "audio.webm")
        return {"transcript": transcript}

    return app


app = create_app()
