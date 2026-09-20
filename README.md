# MustacharAI — Arabic RAG Chatbot for the Tunisian Constitution 2022

A lightweight Retrieval-Augmented Generation (RAG) chatbot that answers
questions about the text and articles (فصول) of the Tunisian Constitution of
2022, in Arabic, using Gemini 1.5 Flash + Google embeddings stored in
ChromaDB, with a Streamlit chat UI.

## Project Structure

```
.
├── README.md
├── constitution-2022.pdf
├── requirements.txt
├── ingest.py       # Reads PDF, splits text, creates vector database
└── app.py          # Streamlit Chatbot UI
```

## Setup

1. Create and activate a virtual environment:

```bash
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Get your Gemini API key from [Google AI Studio](https://aistudio.google.com/)
   and create a `.env` file (see `.env.example`):

```
GOOGLE_API_KEY="your-gemini-api-key-here"
```

> Prefer OpenRouter? Swap `ChatGoogleGenerativeAI` for
> `langchain_community.chat_models.ChatOpenAI` pointing at
> `https://openrouter.ai/api/v1`.

## Index the PDF

Extract the Arabic text from `constitution-2022.pdf`, split it into chunks,
and save them locally into a ChromaDB vector database:

```bash
python ingest.py
```

## Run the App

```bash
streamlit run app.py
```

## Notes for Arabic RAG

- **Arabic PDF extraction:** Arabic text inside PDFs can come out backwards or
  with broken letters. `pypdf`/`pdfplumber` usually work well, but always
  verify the extracted text.
- **Multilingual embeddings:** `text-embedding-004` (or HuggingFace's
  `BAAI/bge-m3`) understands Arabic well.
- **Lightweight LLM:** Gemini 1.5 Flash is fast and cheap, with strong native
  Arabic understanding.

## Improvements (Optional)

- **Metadata extraction:** split by article directly (regex on `الفصل \d+`)
  instead of arbitrary character chunking.
- **OpenRouter:** replace the LLM with
  `ChatOpenAI(base_url="https://openrouter.ai/api/v1", api_key=..., model="deepseek/deepseek-chat")`.