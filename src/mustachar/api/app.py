"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel, Field

from mustachar.core.settings import settings
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

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    @app.post("/api/v1/speak")
    async def speak(body: SpeakRequest) -> Response:
        audio = await tts_full(body.text, voice=body.voice)
        return Response(content=audio, media_type="audio/mpeg")

    return app


app = create_app()
