# multilingual-e5-small over bge-m3

The embedding model is `intfloat/multilingual-e5-small` (~118M params, ~470MB), not `bge-m3` (~570M params, ~2.2GB).

Stage 2 (Reformulation) already translates Darja into formal MSA before vector search. The embedding model only performs MSA-to-MSA similarity matching — cross-lingual capability is unnecessary. On CPU, `e5-small` computes embeddings in ~20–30ms vs. ~120–180ms for `bge-m3`. This saves ~100ms per search without degrading legal retrieval precision.

Considered options: bge-m3 (rejected — paying for unused cross-lingual capacity), paraphrase-multilingual-MiniLM (considered but e5-small has better Arabic benchmarks).
