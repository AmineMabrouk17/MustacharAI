# MustacharAI

A voice-native AI engine that enables real-time spoken interactions in Tunisian Darja backed by deterministic legal grounding in official Tunisian legal codes.

## Language

**Pipeline Stage**:
One discrete unit in the voice-to-voice flow (STT → Reformulation → Retrieval → Generation → TTS).
_Avoid_: step, phase, component

**Reformulation**:
Translating spoken Darja intent into formal MSA legal search terms for vector retrieval.
_Avoid_: translation, transformation, mapping

**Fasl (فصل)**:
An individual statutory article within a legal code. The atomic unit of retrieval and citation.
_AAvoid_: article, clause, provision

**Majalla (مجلة)**:
An official Tunisian legal code (e.g., مجلة الالتزامات والعقود = Code des Obligations et des Contrats).
_Avoid_: law, code, statute

**JORT (الرائد الرسمي)**:
Journal Officiel de la République Tunisienne — official gazette publishing decrees and laws.
_Avoid_: gazette, official journal

**Darja**:
Spoken Tunisian Arabic dialect used for user interaction. Written in Arabic script for TTS compatibility.
_Avoid_: Tunisian Arabic, dialect, slang

**MSA**:
Modern Standard Arabic (Fusha) used in written legal documents and published codes.
_Avoid_: Arabic, classical Arabic, Fus'ha

**Threshold Short-Circuit**:
Skipping LLM inference when vector search similarity < 0.65 to save latency and prevent hallucinations.
_Avoid_: early exit, fallback skip

**Code-Switching**:
Natural Tunisian speech pattern mixing Darja grammar with MSA/French legal terminology in a single sentence.
_Avoid_: bilingual, mixed language

**Zero-Transcoding**:
Passing browser-recorded audio (webm/opus) directly to Groq Whisper without server-side format conversion.
_Avoid_: pass-through, direct forwarding

**Corpus**:
The indexed collection of Tunisian legal texts stored as embeddings in ChromaDB.
_Avoid_: knowledge base, database, documents
