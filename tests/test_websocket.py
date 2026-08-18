"""Tests for the WebSocket streaming endpoint."""

import pytest
from starlette.testclient import TestClient

from mustachar.app import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_ws_echo_binary_frame(client: TestClient) -> None:
    with client.websocket_connect("/api/v1/stream") as ws:
        payload = b"\x00\x01\x02\xff"
        ws.send_bytes(payload)

        # Response 1: Status JSON
        status_msg = ws.receive_json()
        assert status_msg["type"] == "status"
        assert status_msg["stage"] == "listening"
        assert status_msg["bytes_received"] == len(payload)

        # Response 2: Transcript JSON
        transcript_msg = ws.receive_json()
        assert transcript_msg["type"] == "transcript"
        assert "darja_text" in transcript_msg
        assert "latency_ms" in transcript_msg


def test_ws_echo_multiple_frames(client: TestClient) -> None:
    with client.websocket_connect("/api/v1/stream") as ws:
        for i in range(5):
            payload = bytes([i]) * 64
            ws.send_bytes(payload)

            # Consume status message
            status_msg = ws.receive_json()
            assert status_msg["type"] == "status"
            assert status_msg["bytes_received"] == len(payload)

            # Consume transcript message
            transcript_msg = ws.receive_json()
            assert transcript_msg["type"] == "transcript"


def test_ws_graceful_disconnect(client: TestClient) -> None:
    # First connection session
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_bytes(b"ping")
        ws.receive_json()  # status
        ws.receive_json()  # transcript
    # Exiting 'with' block sends close frame cleanly

    # Second connection session to verify server handles re-connection cleanly
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_bytes(b"still alive")
        status_msg = ws.receive_json()
        assert status_msg["type"] == "status"
        assert status_msg["bytes_received"] == len(b"still alive")
        ws.receive_json()  # transcript
