"""Tests for the WebSocket echo endpoint."""

import pytest
from starlette.testclient import TestClient

from mustachar.api.app import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_ws_echo_binary_frame(client: TestClient) -> None:
    with client.websocket_connect("/api/v1/stream") as ws:
        payload = b"\x00\x01\x02\xff"
        ws.send_bytes(payload)
        assert ws.receive_bytes() == payload


def test_ws_echo_multiple_frames(client: TestClient) -> None:
    with client.websocket_connect("/api/v1/stream") as ws:
        for i in range(5):
            payload = bytes([i]) * 64
            ws.send_bytes(payload)
            assert ws.receive_bytes() == payload


def test_ws_graceful_disconnect(client: TestClient) -> None:
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_bytes(b"ping")
        ws.receive_bytes()
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_bytes(b"still alive")
        assert ws.receive_bytes() == b"still alive"
