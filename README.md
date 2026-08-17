# ⚖️ MustacharAI (مستشار تونس)
> **Engineering Specification & Architectural Vision for a Low-Latency Dialectal Legal Voice AI**

[![Project Status: Architectural Blueprint](https://img.shields.io/badge/Status-Architectural_Blueprint-blue.svg)]()
[![Inference: Groq Cloud LPU](https://img.shields.io/badge/Inference-Groq_LPU-orange.svg)](https://groq.com/)
[![Target End-to-End Latency: <1000ms](https://img.shields.io/badge/Target_Latency-%3C1000ms-brightgreen.svg)]()
[![Domain: Tunisian Legal & Constitutional AI](https://img.shields.io/badge/Domain-Tunisian_Law-red.svg)]()

---

## 🎯 Executive Summary & Vision

**MustacharAI** is an engineering blueprint for an open-source, voice-native AI engine designed to democratize access to the Tunisian legal framework. By synthesizing **dialectal Speech-to-Text (STT)**, **cross-lingual Retrieval-Augmented Generation (RAG)**, and **neural speech synthesis (TTS)**, MustacharAI enables real-time spoken interactions in **Tunisian Darja** backed by 100% deterministic legal grounding in official legal codes (*Majallat*, *Doustour*, and *JORT*).

The core technical objective is solving the **Dialect-to-Statute Domain Gap** while maintaining sub-second voice-to-voice response times ($< 1000\text{ ms}$) on zero-GPU host infrastructure.

---

## 🚨 The Core Engineering Challenges

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      THE DIALECT-TO-STATUTE GAP                         │
├───────────────────────────────────┬─────────────────────────────────────┤
│ User Speech Input (Darja)         │ Official Legal Corpus (MSA / French) │
├───────────────────────────────────┼─────────────────────────────────────┤
│ Spoken, informal, fluid syntax   │ Written, formal, rigid legal codes  │
│ e.g., "Patroune torodni"          │ e.g., "الطرد التعسفي من المؤجر"    │
└───────────────────────────────────┴─────────────────────────────────────┘
```

Designing an automated legal voice assistant for Tunisia presents three non-trivial engineering constraints:

### 1. Cross-Lingual & Dialectal Semantic Asymmetry
Tunisian legal text is published exclusively in **Modern Standard Arabic (MSA)** or **French**. However, target users query the system in spoken **Tunisian Darja**. Traditional dense vector models trained on standard Arabic often fail to bridge informal dialectal queries to formal statutory terminology without semantic intermediate transformation.

### 2. Sub-Second Latency Budget for Conversational AI
Human conversational flow breaks down when system latency exceeds $1,000\text{ ms}$. In a multi-stage pipeline (*Voice $\to$ Text $\to$ Query Transformation $\to$ Vector Search $\to$ LLM Reasoning $\to$ Voice*), each sub-component must operate within strict millisecond budgets.

### 3. Zero-Hallucination Legal Grounding
Unlike creative conversational agents, legal systems require **strict factual determinism**. The engine must never extrapolate or generate non-existent statutory articles (*Fasl*). If a legal text does not exist in the retrieved context, the system must deterministically fail-safe.

---

## 🏗️ System Architecture & Data Flow

MustacharAI utilizes a decoupled, asynchronous pipeline where heavy neural compute is offloaded to specialized hardware LPUs (Language Processing Units) in the cloud, while state and retrieval remain localized.

```
                  ┌─────────────────────────────────────────┐
                  │   User Spoken Input (Tunisian Darja)    │
                  └────────────────────┬────────────────────┘
                                       │ Audio Stream
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │    1. Speech-to-Text (Groq Whisper)     │
                  └────────────────────┬────────────────────┘
                                       │ Darja Transcript (~150ms)
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │ 2. Semantic Query Reformulator (Llama)  │
                  └────────────────────┬────────────────────┘
                                       │ MSA Legal Terms (~50ms)
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │ 3. Dense Vector Retrieval (ChromaDB)    │
                  └────────────────────┬────────────────────┘
                                       │ Exact Statutory Clauses (~50ms)
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │  4. Grounded Reasoning Engine (Llama)   │
                  └────────────────────┬────────────────────┘
                                       │ Darja Text in Arabic Script (~250ms)
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │  5. Neural Audio Synthesizer (Edge-TTS) │
                  └────────────────────┬────────────────────┘
                                       │ Audio Stream (~200ms)
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │    Tunisian Audio Streamed to User      │
                  └─────────────────────────────────────────┘
```

---

## ⏱️ System Performance Budget

To maintain natural voice interaction, total processing time is capped at **700ms - 900ms**:

| Pipeline Stage | Sub-System | Target Latency | Optimization Mechanism |
| --- | --- | --- | --- |
| **Stage 1: STT** | Groq `whisper-large-v3` | **~150 ms** | Cloud LPU acceleration with language prompt forcing |
| **Stage 2: Reformulation** | Groq `llama-3.3-70b` | **~50 ms** | Low token generation ($<30$ tokens) for MSA keyword mapping |
| **Stage 3: Vector Search** | Local ChromaDB / `bge-m3` | **~50 ms** | Pre-computed embeddings with HNSW indexing |
| **Stage 4: LLM Generation** | Groq `llama-3.3-70b` | **~250 ms** | High token throughput ($>250$ t/s) with low temperature |
| **Stage 5: TTS Synthesis** | Microsoft Edge-TTS | **~200 ms** | Direct byte-stream audio output buffering |
| **TOTAL TARGET** | **End-to-End Pipeline** | **~700 ms** | **Sub-second real-time voice response** |

---

## ⚙️ Core Engineering Design Principles

### Principle 1: Dialectal Semantic Bridging
Direct semantic lookup between raw Darja audio transcripts and MSA legal vectors leads to low retrieval recall. MustacharAI introduces a **Pre-Retrieval Query Transformation Layer**. An ultra-fast LLM call maps dialectal expressions (*e.g., "Kifech nekri dar?"*) into formal statutory taxonomy (*e.g., "عقد كراء العقارات المبنية"*) prior to querying the vector database.

### Principle 2: Article-Boundary Structure Preservation
Standard fixed-character chunking (e.g., 500-token splitting) destroys legal semantics by cutting clauses mid-sentence. MustacharAI enforces **Regex Structural Chunking**, isolating legal units strictly by statutory markers (*`r"(?=\b(?:الفصل|Article)\s+...)"`*). This ensures every vector chunk contains a complete, self-contained legal rule.

### Principle 3: Phonetic Script Alignment for TTS
Neural TTS engines for Arabic dialects require text formatted strictly in **Arabic Script**. Generating dialectal responses in Arabizi/Franco-Arab (*e.g., "3aslema"*) causes speech synthesis artifacts. System prompts strictly constrain the LLM generation layer to output dialectal Tunisian written entirely in Arabic characters (*e.g., "عصلمة، حسب الفصل..."*).

### Principle 4: Decoupled Edge/Cloud Compute
By delegating neural inference (STT and LLM generation) to Groq's cloud-hosted LPUs, host servers require no local GPU hardware. Host machines only run lightweight embedding vector searches and audio socket streaming, allowing the system to scale cost-effectively on standard CPU cloud infrastructure.

---

## 🛠️ System Hardware & Infrastructure Footprint

```
                       MUSTACHAR-AI HOST INFRASTRUCTURE
 ┌────────────────────────────────────────────────────────────────────────┐
 │  HOST SERVER (Standard CPU Node)                                       │
 │  ├── Memory Footprint: ~2.5 GB RAM (Local Embeddings + DB Index)      │
 │  ├── Compute: 2 to 4 vCPUs (FastAPI + WebSockets Audio Handler)        │
 │  └── Storage: ~10 GB SSD (Legal Vector Index + Audio Caching)          │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │ Async REST / WebSockets API
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │  EXTERNAL CLOUD API SERVICES                                           │
 │  ├── Groq LPU Cluster: Whisper-v3 STT & Llama-3.3-70B LLM              │
 │  └── Microsoft Neural Network: Edge-TTS Engine (`ar-TN-HediNeural`)    │
 └────────────────────────────────────────────────────────────────────────┘
```

---

## 🔒 Safety, Guardrails & Governance

1. **Zero Extrapolation:** The LLM prompt architecture enforces a strict system rule: if the context returned from the vector store does not explicitly answer the query, the engine outputs a pre-defined fallback message advising consult with a certified attorney.
2. **Mandatory Article Citation:** Every affirmative legal statement generated by the system must include the source name (*Majalla*) and specific clause identifier (*Fasl*).
3. **Non-Counsel Disclaimer:** The system is explicitly designed as a **civic research engine**, not a legal legal entity. It operates under strict disclaimer parameters disclaiming official attorney-client privilege.

---

## 📜 License

This architectural specification and open-source implementation of **MustacharAI** are released under the **MIT License**. Free for civic, educational, and non-commercial development.
