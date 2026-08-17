"""Tests for the WebSocket streaming endpoint."""

from starlette.testclient import TestClient

from mustachar.app import app


def test_ws_echo_binary_frame() -> None:
    with TestClient(app).websocket_connect("/api/v1/stream") as ws:
        payload = b"\x00\x01\x02\xff"
        ws.send_bytes(payload)
        status_msg = ws.receive_json()
        assert status_msg["type"] == "status"
        assert status_msg["stage"] == "listening"
        assert status_msg["bytes_received"] == len(payload)
        transcript_msg = ws.receive_json()
        assert transcript_msg["type"] == "transcript"
        assert "darja_text" in transcript_msg
        assert "latency_ms" in transcript_msg


def test_ws_echo_multiple_frames() -> None:
    with TestClient(app).websocket_connect("/api/v1/stream") as ws:
        for i in range(5):
            payload = bytes([i]) * 64
            ws.send_bytes(payload)
            status_msg = ws.receive_json()
            assert status_msg["type"] == "status"
            assert status_msg["bytes_received"] == len(payload)
            transcript_msg = ws.receive_json()
            assert transcript_msg["type"] == "transcript"


def test_ws_graceful_disconnect() -> None:
    client = TestClient(app)
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_bytes(b"ping")
        ws.receive_json()
        ws.receive_json()
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_bytes(b"still alive")
        status_msg = ws.receive_json()
        assert status_msg["type"] == "status"
        assert status_msg["bytes_received"] == len(b"still alive")
        ws.receive_json()
