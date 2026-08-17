"""Sample test to verify pytest, httpx, and ruff work."""

import pytest
from httpx import ASGITransport, AsyncClient


def test_sample_math() -> None:
    assert 1 + 1 == 2


def test_sample_string() -> None:
    assert "mustachar".upper() == "MUSTACHAR"


@pytest.mark.asyncio
async def test_httpx_async_client() -> None:
    """Verify httpx async transport is wired correctly."""

    def dummy_app() -> None:
        return None

    async with AsyncClient(
        transport=ASGITransport(app=dummy_app),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as client:
        assert client.base_url == "http://testserver"
