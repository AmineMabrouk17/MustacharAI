# MustacharAI — مستشار القانوني

AI-powered **Arabic legal assistant** for Tunisian law. It answers questions in
Arabic (or Tunisian Darija) using Retrieval-Augmented Generation over a corpus
of ~15 Tunisian legal codes (~3500 indexed articles/فصول), grounding every
answer in citations, with optional **voice input (STT)**, **spoken answers
(TTS)**, and a **switchable LLM provider**: Groq, Gemini, or **your own
OpenRouter key + model** configured straight from the UI.

- **Backend** — FastAPI on `:8000` (REST + WebSocket streaming), ChromaDB
  vector store (`sentence-transformers` E5 embeddings).
- **Frontend** — Next.js (React) on `:3000`, RTL Arabic UI.

```
┌─────────────┐   REST + WS    ┌──────────────────────────────────────────┐
│  Next.js UI │ ─────────────► │  FastAPI :8000                            │
│    :3000    │                │  reformulate → retrieve → generate (RAG)  │
└─────────────┘                │  LLM: Groq │ Gemini │ OpenRouter (UI-set) │
                               └──────────────────────────────────────────┘
```

## Prerequisites

- Python **3.11+**
- Node.js **18+** (npm)
- Git

## 1. Clone the repository

```bash
git clone https://github.com/AmineMabrouk17/MustacharAI.git
cd MustacharAI
```

The Tunisian legal PDFs (the corpus) are committed at the repo root
(`*.pdf`), so a fresh clone already contains all source material.

## 2. Backend setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"          # or: make install
```

## 3. Environment (.env)

```bash
cp .env.example .env
# edit .env — minimum for the app to work:
#   GROQ_API_KEY=your-groq-api-key
```

| Variable               | Required | Purpose                                    |
| ---------------------- | :------: | ------------------------------------------ |
| `GROQ_API_KEY`         | ✅       | Groq LLM + Whisper speech-to-text          |
| `GOOGLE_API_KEY`       | optional | Gemini provider (OAuth `AQ.` key)          |
| `GROQ_CHAT_MODEL`      | optional | Default LLM (default `allam-2-7b`)         |
| `RETRIEVAL_THRESHOLD`  | optional | Min similarity to keep a chunk (0.84)      |
| `CHROMA_PERSIST_DIR`   | optional | Vector DB location (default `data/chroma_db`) |

> **OpenRouter** needs no environment variable — configure it at runtime in
> the web UI (header button "OpenRouter" → paste your `sk-or-v1-...` key and
> model ID, e.g. `openai/gpt-6-luna`). It is validated against OpenRouter and
> persisted server-side.

## 4. Build the legal index (first launch only)

```bash
# Low-RAM boxes (2 GB): keep a single embedding thread
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false OPENBLAS_NUM_THREADS=1

# Index every legal PDF in the current directory (repo root)
python -m mustachar.cli.index --dir . --reset
```

This creates the `legal_corpus` ChromaDB collection (~3500 chunks). Use
`--dry-run` to preview parsed articles without writing. Re-run with `--reset`
to rebuild from scratch. The vector DB lives in `data/chroma_db/` (gitignored).

## 5. Run the backend

```bash
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false OPENBLAS_NUM_THREADS=1
uvicorn mustachar.api.app:app --host 0.0.0.0 --port 8000
```

Health check: `curl http://localhost:8000/health` → `{"status":"healthy"}`.

## 6. Run the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000** — the UI connects to the backend on
`localhost:8000` directly (no proxy needed). Chat in Arabic, toggle the LLM
provider from the top-right select, and configure your OpenRouter key/model
from the "OpenRouter" button.

## 7. LLM providers

| Provider   | How to enable                                            | Tested models                                   |
| ---------- | -------------------------------------------------------- | ----------------------------------------------- |
| Groq       | `GROQ_API_KEY` in `.env`                                  | `qwen/qwen3.8-27b`, `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `allam-2-7b` |
| Gemini     | `GOOGLE_API_KEY` in `.env`                                 | `gemini-flash-latest`, `gemini-pro-latest`      |
| OpenRouter | UI button (your key + model ID)                            | any model ID, e.g. `openai/gpt-6-luna`          |

Only models verified to work with real keys are shipped in the picker. If a
provider fails (quota, overload, invalid key) the **real error message** is
shown in the UI (red bubble) with the technical detail.

## API (summary)

| Method | Endpoint                     | Purpose                                |
| ------ | ---------------------------- | -------------------------------------- |
| GET    | `/health`                    | Health check                           |
| POST   | `/api/v1/ask`                | One-shot grounded answer (JSON)        |
| WS     | `/api/v1/stream`             | Streaming chat (answer + citations)    |
| GET    | `/api/v1/models`             | List providers/models + active         |
| POST   | `/api/v1/models/active`      | Switch active LLM                      |
| POST   | `/api/v1/models/openrouter`  | Register OpenRouter key + model        |
| GET    | `/api/v1/documents`          | List indexed documents                 |
| POST   | `/api/v1/documents/upload`   | Upload & index a PDF/TXT from the UI   |
| DELETE | `/api/v1/documents/{source}` | Remove one source's chunks             |

## Quality checks

```bash
make check    # ruff lint + mypy typecheck + pytest (all LLM calls mocked)
```

## Troubleshooting

- **Out of memory / slow first start** — must run with the
  `OMP_NUM_THREADS=1 …` env vars above; the first index/build downloads the
  embedding model.
- **`429` / `503` from the model** — upstream quota or rate limit (free
  OpenRouter models are often queued). The UI shows the real error; switch
  model/provider or wait, and for OpenRouter prefer a non-`:free` model.
- **Stale answers after editing the corpus** — re-index:
  `python -m mustachar.cli.index --dir . --reset`.
- **Gemini quota exhausted** — a `429 You exceeded your current quota` is the
  key's billing/plan, not a code issue.

## Repository layout

```
├── src/mustachar/
│   ├── api/           # FastAPI app, WebSocket streaming, rate limiting
│   ├── core/          # settings (.env)
│   ├── infra/         # llm_client (Groq/Gemini/OpenRouter), groq_client, chroma_client
│   └── pipeline/      # reformulator → retrieval → generator orchestrator
├── frontend/          # Next.js UI (Arabic RTL)
├── data/              # gitignored: chroma_db, OpenRouter config, active model
├── tests/             # pytest suite (mocked LLM/embeddings)
└── *.pdf              # Tunisian legal code corpus (committed)
```