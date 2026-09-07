# Threshold Short-Circuit

When Stage 3 (Retrieval) returns no chunks above the 0.65 cosine similarity threshold, Stage 4 (LLM Generation) is skipped entirely. A pre-written static Darja fallback response is returned immediately.

_Amendment (issue #16): the threshold is cosine similarity, not L2 distance. The collection is created with `hnsw:space: cosine`, so Chroma returns cosine distances (0 = identical). Chunks are kept when `distance <= 1.0 - threshold` (similarity >= 0.65)._

This saves ~250ms of LLM compute and 100% of API cost on queries with no legal match. More importantly, it prevents hallucination — an LLM given no context but asked to answer a legal question will fabricate citations. Short-circuiting enforces the zero-hallucination guarantee at the architecture level, not just the prompt level. Because the distance space is fixed at collection creation, switching to cosine requires re-indexing the Corpus (ADR-0006) via `python -m mustachar.cli.index`.

Considered options: always-call-LLM with prompt-level fallback (rejected — prompt constraints are probabilistic, not deterministic).
