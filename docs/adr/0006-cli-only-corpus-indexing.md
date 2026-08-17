# CLI-only Corpus Indexing

Legal corpus ingestion runs as a local CLI command (`python -m mustachar.cli.index`), not as an HTTP endpoint on the FastAPI server.

Indexing is a CPU-intensive operation (PDF parsing, regex chunking, embedding computation) that can take minutes for a full legal code. Exposing it as an API endpoint creates an abuse vector — an attacker could trigger repeated re-indexing, exhausting host CPU and memory. CLI-only access ensures only authorized operators can modify the corpus.

Considered options: admin-only API endpoint with auth (rejected — adds auth complexity for a low-frequency operation), background worker queue (premature for v1).
