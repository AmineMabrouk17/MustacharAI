# French Neural TTS Voice for French Answers

Synthesized answers with `fr-FR-HenriNeural` instead of `ar-TN-HediNeural`. Answers leave the generation stage in French (ADR-0005 amendment, issue #38), so the voice must now render French text. Issue #39 asks for the formal A/B that motivated this swap.

## A/B comparison (2026-09-08)

A representative grounded answer — 206 characters, the "congé annuel" case citing Article 125/127 du Code du travail — was synthesized over Edge-TTS with the previous Tunisian voice and every `fr-FR` candidate. All candidates were confirmed present in the runtime `edge_tts.list_voices()` snapshot taken at test time.

**Naturalness rubric** (French orthography rendered as speech): correct French phoneme inventory (nasal vowels /ɛ̃/ /ɑ̃/ /ɔ̃/, /u/ vs /y/), native liaison and elision, phrase-final stress and intonation. A voice built for another language fails this by construction when speaking French.

| Voice | Locale | French phonology/prosody | Latency (206-char answer) |
|---|---|---|---|
| `ar-TN-HediNeural` | ar-TN | Foreign: Tunisian phoneme inventory, Arabic stress and intonation on French text | ~4,270 ms |
| `fr-FR-HenriNeural` | fr-FR | Native: clean liaison, nasal vowels, natural sentence intonation | ~1,020 ms |
| `fr-FR-DeniseNeural` | fr-FR | Native (female) | ~929 ms |
| `fr-FR-EloiseNeural` | fr-FR | Native (female) | ~1,675 ms |
| `fr-FR-RemyMultilingualNeural` | fr-FR | Native (multilingual, slower) | ~2,945 ms |
| `fr-FR-VivienneMultilingualNeural` | fr-FR | Native (multilingual, slower) | ~3,388 ms |

## Decision

Winner: `fr-FR-HenriNeural` — a native French neural voice, male like the Tunisian voice it replaces, with low synthesis latency. Wired as the default via `settings.tts_voice` (env-overridable with `TTS_VOICE`, matching the configurable-model pattern used for the Groq models in #33/#42).

Runtime guard in `edge_tts_client.synthesize`: the configured voice is cross-checked against the `list_voices()` snapshot on first use (process-lifetime cache, so the one-off lookup does not tax the per-turn latency budget). If the requested voice is retired, it falls back to the configured default, then to the first available French backup. This mirrors the Groq model-retirement incident (#33): config pointing at a removed voice otherwise yields silent audio.

Considered options: keep `ar-TN-HediNeural` (rejected — foreign-accented French), pick a multilingual fr-FR voice (rejected — slower, and answers are mono-language French).