# MISSIONWISE AI — Missing Dependencies & Integration Boundaries

This document records all external services, credentials, binary tools, and model weights required for full production operation, along with their active graceful fallback mechanisms.

---

## 1. LLM Provider API Key (`GEMINI_API_KEY`)

| Property | Details |
|---|---|
| **Purpose** | Powers grounded query answering, STAIR L2 ToC leaf selection, failure chain extraction, and KG entity extraction. |
| **Required Env Var** | `GEMINI_API_KEY` in `.env` |
| **Recommended Model** | `gemini-3.5-flash` (or `gemini-2.0-flash` / `gemini-2.5-flash-lite`) |
| **Integration Boundary** | Provider-agnostic `LLMClient` interface (`backend/app/services/llm/client.py`) with automatic fallback chain and retry logic. |
| **Active Fallback** | When the key is absent or hits quota (HTTP 429/503), the system gracefully uses: <br>1. **Extractive Fallbacks** (`_extractive_fallback` in `indexer.py`, `demo_cache.py`, and `reconstructor.py`) that parse candidate evidence chunks directly without LLM calls.<br>2. **BM25-ToC Selector** for section retrieval.<br>3. **Pre-warmed Demo Cache** (`data/demo/demo_cache.json`) for live demonstrations. |
| **Action for User** | Set `GEMINI_API_KEY=<your-key>` in `.env` for dynamic LLM generation. |

---

## 2. Server-Side Text-To-Speech (`piper`)

| Property | Details |
|---|---|
| **Purpose** | Fast, local neural text-to-speech synthesis on the backend. |
| **Required Binaries/Files** | `piper` executable in PATH and ONNX voice model (e.g. `en_US-lessac-medium.onnx`). |
| **Required Env Vars** | `PIPER_BINARY_PATH=piper`, `PIPER_VOICE_PATH=/app/model_cache/en_US-lessac-medium.onnx` |
| **Integration Boundary** | `TTSService` (`backend/app/services/voice/tts.py`). |
| **Active Fallback** | When Piper or voice weights are absent, returns `used_fallback=True` and the frontend seamlessly uses the browser's native `window.speechSynthesis` API. |
| **Action for User** | Optional. Browser speech synthesis works automatically out of the box with zero setup. |

---

## 3. Server-Side Speech-To-Text (`faster-whisper`)

| Property | Details |
|---|---|
| **Purpose** | Streaming and chunked speech recognition on the backend with aerospace vocabulary prompting. |
| **Required Model** | Whisper ONNX weights (`tiny.en` or `base.en`). |
| **Integration Boundary** | `STTService` (`backend/app/services/voice/stt.py`). |
| **Active Fallback** | When server-side STT is unavailable or disabled, the frontend activates the browser's native `webkitSpeechRecognition` / Web Speech API. |
| **Action for User** | Optional. In Docker, `faster-whisper` downloads weights to `/app/model_cache` automatically on first voice query. |

---

## 4. STAIR L3/L4 Fine-Tuned LoRA Adapter

| Property | Details |
|---|---|
| **Purpose** | Fine-tuned query-to-leaf section selector trained on ToC pairs. |
| **Required Files** | LoRA adapter directory specified by `STAIR_LORA_ADAPTER_PATH`. |
| **Integration Boundary** | `FineTunedSTAIRSectionSelector` (`backend/app/services/retrieval/section_selector.py`). |
| **Active Fallback** | When untrained, `is_trained_model_available()` returns `False` and delegates to STAIR L2 (`STAIRInspiredSectionSelector`) or BM25-ToC without blocking the application. |
| **Action for User** | Run `python scripts/generate_training_data.py` followed by `python scripts/train_stair.py` on a GPU instance (e.g. Google Colab) to train weights if desired. |

---

## 5. Seed Space Mission Incident Reports

| Property | Details |
|---|---|
| **Status** | **Present & Ingested**. Three core NASA reports are committed in `data/raw_documents/`: <br>- `mars_climate_orbiter_phase1_1999.pdf` (1.46 MB)<br>- `apollo_13_review_board_1970.pdf` (9.02 MB)<br>- `mars_polar_lander_jpl_2000.pdf` (9.82 MB) |
| **Source Provenance** | Public NASA reports archived with source URL and public domain licences in `manifest.json`. |
| **Additional Reports** | Run `python scripts/download_seed_reports.py` to fetch additional public reports. |
