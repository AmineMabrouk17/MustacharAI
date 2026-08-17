"""FastAPI application factory."""

from fastapi import FastAPI

from mustachar.core.settings import settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    return app


app = create_app()
