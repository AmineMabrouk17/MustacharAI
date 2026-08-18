# Local ChromaDB over Cloud Vector DB

Legal vector retrieval runs on a local ChromaDB instance with HNSW indexing in server RAM.

Cloud vector DBs (Qdrant Cloud, Pinecone) add ~70–100ms network ping from North Africa to EU-hosted instances, on top of 5ms query time. Local ChromaDB queries in ~8–15ms with zero network overhead. The complete Tunisian legal corpus (~15,000–25,000 chunks) fits easily in RAM. ChromaDB handles up to 500,000 vectors without degradation.

Cost: $0 forever. Storage is a local directory (`./data/chroma_db`).

Considered options: Qdrant Cloud (rejected for latency and cost), pgvector (rejected for setup complexity at this scale).
