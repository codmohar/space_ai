# MISSIONWISE AI

**Space Mission Engineering Intelligence Platform** (AVISHKAR 2K26 — Problem #10: Space Mission Lessons-Learned Assistant with Cited Answers)  
Team: **ProtoGuys**

> **Safety Notice:** MISSIONWISE is a knowledge-support tool, not a certifier of spacecraft safety. All findings must be verified against the cited primary engineering reports.

---

## Phase 1 Capabilities

- **PostgreSQL 16 + pgvector Schema (Alembic):** Full schema covering auth/audit, documents & versions, hierarchical `document_sections`, `document_chunks` with PDF bounding boxes and `tsvector` lexical search, `document_embeddings` (HNSW), `retrieval_logs`, `conversations`/`messages`/`citations`, and Phase 2+ failure chain & engineering knowledge graph tables.
- **PDF Ingestion Pipeline:**
  - Mandatory `source_url` and `licence` validation (public reports only).
  - Magic-byte (`%PDF-`), MIME, size, and SHA-256 hash-based deduplication.
  - PyMuPDF (`fitz`) text, metadata, `get_toc()` + font-size heading heuristic fallback, and exact bounding-box extraction (`[x0, y0, x1, y1]`).
  - Automatic Tesseract OCR fallback for scanned/low-text pages with mean word confidence and alphanumeric quality checks.
  - Structure- and page-preserving semantic chunking with merged bbox retention.
- **Hybrid Retrieval & Grounded RAG:**
  - `BAAI/bge-small-en-v1.5` embeddings (configurable) + pgvector HNSW dense search + BM25/FTS lexical search + Reciprocal Rank Fusion (RRF) + Cross-Encoder Reranker (`BAAI/bge-reranker-base`).
  - Provider-agnostic `LLMClient` (Gemini default via `GEMINI_API_KEY`) with prompt-injection delimiting and Pydantic JSON validation + retry.
  - Pre-response **Citation Validator** checking chunk/document/page resolution and quote/lexical support before returning answers.
  - **Deterministic Retrieval Confidence** (`Strong`, `Partial`, `Conflicting`, `Insufficient`, `None`) — never LLM self-reported.
  - **Exact Abstention Policy:** low-evidence or ungrounded queries return `"Not found in the available mission reports. More supporting documentation is required."`
- **Frontend Console & Citation Viewer:**
  - Instrument-grade mission-control UI built from `frontend/src/styles/design-tokens.ts`.
  - Resizable split-pane Research Assistant + PDF Citation Viewer (`react-pdf`) that opens directly at the cited page and overlays translucent amber highlights via chunk bounding boxes.

---

## Honest STAIR Implementation Status

MISSIONWISE ships STAIR-style structure-aware retrieval incrementally and labels every level honestly:
- **L1 (Active):** Hierarchical document section index (`document_sections` with `is_leaf` and 3-tier ToC extraction: PDF outline -> font/numbering heuristics -> LLM repair) + `BM25ToCSectionSelector` baseline.
- **L2 (Active — Phase 2):** ToC-aware query-to-leaf selection (`STAIRInspiredSectionSelector`) returning validated leaf section IDs via `POST /api/stair/retrieve`, with Document Explorer ToC tree highlighting.
- **L3 / L4 (Optional GPU Training — Phase 2):** `scripts/generate_training_data.py` + `scripts/train_stair.py` (LoRA fine-tuning + constrained leaf-ID decoding for free Colab/Kaggle GPUs; see [docs/stair_training.md](docs/stair_training.md)), wired behind `FineTunedSTAIRSectionSelector`.

## Evaluation (Phase 2)
Run the retrieval benchmark across `data/evaluation/questions.jsonl` (42 questions including 10 unanswerable):
```bash
python scripts/evaluate_retrieval.py --questions data/evaluation/questions.jsonl
```
Results are saved to `data/evaluation/retrieval_results.json` and served by `GET /api/eval/results` to the Evaluation page. Until executed, the UI displays `"Not yet evaluated"`.

## Voice Assistant (Phase 3)
- **Single Shared Pipeline:** `WS /api/voice/stream`, `POST /api/voice/transcribe`, and `POST /api/voice/synthesize` route through the exact same `RAGService` + `CitationValidator` as `POST /api/chat`.
- **Aerospace-Biased STT & Fallbacks:** Server `faster-whisper` uses an aerospace vocabulary prompt (`Small Forces`, `Newton-seconds`, `Apollo 13`, etc.); falls back to browser Web Speech API (`SpeechRecognition`) and `window.speechSynthesis` if server STT/TTS models are unavailable.
- **Follow-up Memory & Spoken Style:** Resolves follow-ups (`"what was the initial issue?"`, `"explain simpler"`) into standalone questions and outputs concise spoken briefings with identical verified claims, live captions, PTT/hands-free modes, and barge-in/interrupt support.

---

## Quickstart

### 1. Configure Environment
```bash
cp .env.example .env
# Add your GEMINI_API_KEY to .env
```

### 2. Download & Verify 3 Public Seed Reports
```bash
python scripts/download_seed_reports.py
```

### 3. Start Stack via Docker Compose
```bash
docker compose up --build -d
```

### 4. Seed the Knowledge Base
```bash
docker compose exec backend python /scripts/ingest_documents.py --manifest /data/raw_documents/manifest.json
```

### 5. Access Services
- Frontend UI: `http://localhost:5173`
- Backend API & Swagger: `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/api/health`

### 6. Run Tests
```bash
cd backend
pytest -v
```
