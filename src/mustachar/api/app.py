"""FastAPI application factory."""

from fastapi import FastAPI

from mustachar.api.websocket import router as ws_router
from mustachar.core.settings import settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
    )

    app.include_router(ws_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    return app


app = create_app()
