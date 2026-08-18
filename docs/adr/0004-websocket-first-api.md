# WebSocket-first API

The primary API surface is a bidirectional WebSocket for real-time voice streaming. A REST `POST /ask` endpoint exists for file-upload fallback.

REST file upload forces a sequential flow: user talks → uploads full audio → waits for processing → receives full response. Perceived latency: 2.5–3.5 seconds. WebSocket streaming enables overlapping stages: audio chunks stream in while TTS chunks stream back immediately after processing. Perceived latency drops to <400ms after the user finishes speaking.

Considered options: REST-only (rejected for conversational UX), gRPC streaming (rejected — WebSocket has broader browser support).
