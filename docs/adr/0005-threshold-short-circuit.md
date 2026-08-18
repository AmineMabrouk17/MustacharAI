# Threshold Short-Circuit

When Stage 3 (Retrieval) returns no chunks above the 0.65 cosine similarity threshold, Stage 4 (LLM Generation) is skipped entirely. A pre-written static Darja fallback response is returned immediately.

This saves ~250ms of LLM compute and 100% of API cost on queries with no legal match. More importantly, it prevents hallucination — an LLM given no context but asked to answer a legal question will fabricate citations. Short-circuiting enforces the zero-hallucination guarantee at the architecture level, not just the prompt level.

Considered options: always-call-LLM with prompt-level fallback (rejected — prompt constraints are probabilistic, not deterministic).
