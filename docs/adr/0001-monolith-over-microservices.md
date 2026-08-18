# Monolith over Microservices

The 5-stage pipeline (STT → Reformulation → Retrieval → Generation → TTS) runs as a single Python process. Inter-stage communication is function calls, not network requests.

Microservices introduce serialization and network transport delays (~15–30ms per boundary). In a 5-step pipeline, that's 80–120ms of pure latency tax — unacceptable against a 700ms budget. A monolith also eliminates the need for multiple container runners, fitting the target infrastructure (single 4GB VPS).

Considered options: microservices (rejected for latency and cost), serverless functions (rejected for cold-start latency on TTS/LLM stages).
