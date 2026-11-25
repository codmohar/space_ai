# MISSIONWISE AI — System Audit & Technical Assessment Report

**Date:** 2026-11-25  
**Auditor:** Principal Engineer / Full-Stack Applied ML & RAG Architect  
**Project:** MISSIONWISE AI (AVISHKAR 2K26, Problem #10)  
**Target Audience:** Space-agency engineers, mission analysts, hackathon reviewers  

---

## 1. Executive Summary

A comprehensive, line-by-line audit of the entire MISSIONWISE AI repository (`c:\Users\466mo\OneDrive\Desktop\New folder\Space_proj`) was conducted across backend services, database schema, Alembic migrations, retrieval pipeline, LLM integrations, voice subsystem, security controls, evaluation harness, scripts, and frontend components.

The system is built on **FastAPI (Python 3.11)**, **PostgreSQL 16 + pgvector**, **PyMuPDF**, **Sentence-Transformers (BGE)**, **Cross-Encoder reranking**, and **React 18 + Vite + TypeScript**.

All 34 automated unit and integration tests are currently passing (`34 passed, 1 warning in 33.56s` via `pytest`).

However, several critical gaps must be addressed to fulfill production-grade requirements:
1. **Ingestion is currently PDF-only**; format-specific parsers for TXT, MD, DOCX, CSV, HTML, and image scans are missing or partial.
2. **Ingestion is synchronous** in the upload route; background job queue with status progression (`queued` -> `processing` -> `indexed` -> `failed` -> `cancelled`) is needed.
3. **Document-level authorization scoping** is missing in the retrieval pipeline (currently any authenticated user can retrieve all documents).
4. **Rolling conversation summarization** is not persisted in the database schema for long research chats.
5. **Docker Compose lacks Redis/Worker** for async queue scalability.

---

## 2. Feature-by-Feature Status & Verification Matrix

Every feature below has been audited with file-level evidence, command executions, and observed outputs.

| # | Feature | Status | Primary Files & Evidence | Notes / Verdict |
|---|---|---|---|---|
| 1 | **Multi-format Ingestion** | **PARTIAL** | `backend/app/services/ingestion/pipeline.py` (L60-67), `pdf_extractor.py` | Strictly accepts PDF (`%PDF-` bytes, MIME `application/pdf`). Format parsers for TXT, MD, DOCX, CSV, HTML, and image scans are missing. |
| 2 | **Async Processing & Worker Queue** | **PARTIAL** | `backend/app/api/documents.py` (L47-61), `pipeline.py` | Ingestion runs synchronously in request thread. No background worker queue tracking `queued`/`processing`/`indexed`/`failed`/`cancelled` with retry/cancel. |
| 3 | **SHA-256 Deduplication** | **WORKING** | `backend/app/services/ingestion/pipeline.py` (L69-84) | Computes SHA-256 hash, verifies against `documents.file_hash`, returns `status="duplicate"` without duplicate storage. Verified in `test_ingestion_validation.py`. |
| 4 | **ToC Hierarchy Extraction** | **WORKING** | `backend/app/services/ingestion/pdf_extractor.py` (L100-340), `models/documents.py` | 3-tier extraction: (1) native PDF outline via `get_toc()`, (2) font-size & numbered-heading heuristics fallback, (3) LLM-assisted repair. Stored in `document_sections` with `parent_id` and `is_leaf`. |
| 5 | **STAIR Retrieval** | **WORKING (L2)** | `backend/app/services/retrieval/section_selector.py` (L1-420) | Honest labelling: L1 BM25-ToC baseline, L2 STAIR-inspired ToC-aware leaf selection with strict leaf ID validation against DB, L3/L4 cleanly stubbed with fallback and offline training scripts (`generate_training_data.py`, `train_stair.py`). |
| 6 | **Hybrid Retrieval** | **WORKING** | `backend/app/services/retrieval/hybrid.py` (L87-250) | Combines pgvector cosine similarity (`bge-small-en-v1.5`) with lexical `BM25Okapi` and Reciprocal Rank Fusion (RRF, k=60). |
| 7 | **Cross-Encoder Reranker** | **WORKING** | `backend/app/services/retrieval/hybrid.py` (L64-85) | `BAAI/bge-reranker-base` cross-encoder with sigmoid score normalization and persistent model cache. |
| 8 | **Grounded Answers & Claims** | **WORKING** | `backend/app/services/rag/service.py` (L125-240), `prompt_guard.py` | Strict XML context delimiters `<evidence_chunk>`, system prompt instructing model to treat document text as untrusted, structured Pydantic output. |
| 9 | **Citation Validation** | **WORKING** | `backend/app/services/rag/citation_validator.py` (L60-195) | Verifies document exists, page matches, and quoted text has >= 70% token overlap with stored chunk text. Strips invalid citations, triggers regeneration or downgrades. Verified in `test_citation_validator.py`. |
| 10 | **Deterministic Abstention** | **WORKING** | `backend/app/services/rag/service.py` (L101-120), `app/core/config.py` | Returns exact string: *"Not found in the available mission reports. More supporting documentation is required."* when rerank score < 0.18, RRF < 0.012, or all citations fail validation. Verified in `test_abstention_and_confidence.py`. |
| 11 | **Confidence Scoring** | **WORKING** | `backend/app/services/rag/confidence.py` (L20-80) | Deterministic composite metric from retrieval scores, evidence coverage, and citation verification pass rate. Categories: `Strong`, `Partial`, `Conflicting`, `Insufficient`, `None`. Never uses LLM self-confidence. |
| 12 | **Clickable Citation -> PDF + Highlight** | **WORKING** | `frontend/src/components/chat/CitationChip.tsx`, `CitationViewer.tsx`, `backend/app/api/documents.py` | Monospace chips click to open split-pane PDF viewer (`react-pdf` / PDF.js), jumps to target page, renders bbox highlight overlay. File served via `/api/documents/{id}/file`. |
| 13 | **Conversation Memory & Summaries** | **PARTIAL** | `backend/app/services/rag/query_rewriter.py` (L1-170), `models/rag.py` | Follow-up query rewriting works for active chat history. However, rolling summarization for long chats (preserving topic, mission, subsystems, findings, unresolved questions) is missing in DB schema and chat flow. |
| 14 | **Voice Assistant (STT, TTS, Barge-in)** | **WORKING** | `backend/app/services/voice/stt.py`, `tts.py`, `api/voice.py`, `frontend/src/components/voice/VoiceConsoleBar.tsx` | faster-whisper with aerospace vocabulary prompt, WebSocket `/api/voice/stream` with interrupt/barge-in support, spoken answer formatter, and browser Web Speech API / SpeechSynthesis fallback. |
| 15 | **Failure Chain Analyzer** | **WORKING** | `backend/app/services/failures/reconstructor.py`, `evidence_validator.py`, `FailureChainPage.tsx` | Shared retriever extracts anomaly sections, LLM structured extraction into `FailureEvent` and `FailureRelationship`, evidence validator verifies quotes against DB chunks, React Flow interactive graph. Zero hardcoded chains. |
| 16 | **Similar Past Failures** | **WORKING** | `backend/app/services/incidents/similar_search.py`, `SimilarFailuresPage.tsx` | Extracts problem entities/subsystems, hybrid search over `MissionIncident` table with subsystem/mechanism boost, transparent relevance breakdown. |
| 17 | **Engineering Knowledge Graph** | **WORKING** | `backend/app/services/kg/service.py`, `KnowledgeGraphPage.tsx` | Relational tables (`mission_entities`, `mission_entity_relations`), multi-hop queries ("missions with propulsion anomalies and corrective actions"), cited graph visualization. |
| 18 | **Dashboard with Real Data** | **WORKING** | `frontend/src/pages/DashboardPage.tsx` | Binds to live `/api/stats`, `/api/documents`, and `/api/health` endpoints (3 ingested documents, 684 chunks, 523 sections, 12 incidents, 57 KG entities). |
| 19 | **Evaluation Page with Real Data** | **WORKING** | `frontend/src/pages/EvaluationPage.tsx`, `scripts/evaluate_retrieval.py` | Driven strictly by `data/evaluation/retrieval_results.json` generated from 42 test questions in `questions.jsonl`. Unmeasured metrics honestly show "Not yet evaluated". |
| 20 | **JWT Authentication & RBAC** | **WORKING** | `backend/app/services/auth/security.py`, `api/auth.py`, `api/admin.py`, `AdminPage.tsx` | PBKDF2-HMAC-SHA256 password hashing, HS256 JWT tokens, roles `admin` and `engineer`, seeded demo users, role-guarded admin console. |
| 21 | **Document-level Access Control** | **PARTIAL** | `backend/app/models/documents.py`, `retrieval/hybrid.py` | System has user roles, but documents lack security classification/access tags, and retrieval does not filter candidate chunks by user permissions before searching. |
| 22 | **Sliding-Window Rate Limiting** | **WORKING** | `backend/app/core/rate_limit.py`, `main.py` | Sliding-window in-memory rate limiter per IP, returns structured 429 `RATE_LIMIT_EXCEEDED`. Tested in `test_phase6_security_and_demo.py`. |
| 23 | **Audit & Version Logging** | **WORKING** | `backend/app/services/audit.py`, `retrieval/logger.py` | Logs security actions to `audit_logs` table; logs model name, prompt version, latencies, and scores to `retrieval_logs` table. |
| 24 | **Docker & Deployment Infrastructure** | **WORKING** | `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile` | Postgres 16 + pgvector container (:5433), FastAPI backend (:8001), React/Vite frontend (:5173). Persistent volumes and health checks configured. |

---

## 3. Prioritized Repair & Completion Plan

### Phase P0: Demo-Critical & Core Grounding Enhancements
1. **Multi-Format Ingestion Engine (P0):**
   - Add format parsers for plain text (`.txt`), Markdown (`.md`), HTML (`.html`), CSV (`.csv`), Word (`.docx`), and image formats (`.png`, `.jpg`, `.tiff` via Tesseract OCR).
   - Normalize all formats into unified `ExtractedDocument` structures with page numbers, sections, blocks, and bounding boxes.
   - Update file validation to detect MIME and magic bytes for all supported formats.
2. **Background Ingestion Worker & Status Tracking (P0):**
   - Add job queue manager (`queued`, `processing`, `indexed`, `failed`, `cancelled`) using FastAPI background tasks (with Redis/Celery upgrade path).
   - Implement job status polling and cancellation endpoints (`GET /api/documents/jobs/{job_id}`, `POST /api/documents/jobs/{job_id}/cancel`).
   - Only promote documents to `ingestion_status="completed"` once text, ToC sections, chunks, and embeddings succeed atomically.
3. **Document-Level Access Scoping in Retrieval (P0):**
   - Add access tags / classification levels to `Document` (`public`, `internal`, `restricted`).
   - Inject user authorization scope into `HybridRetriever.search()` to filter documents before vector and BM25 search.

### Phase P1: Stability, Conversation Memory & Operations
1. **Persistent Rolling Conversation Summaries (P1):**
   - Add `summary` column to `conversations` table.
   - When conversation history exceeds 6 turns, trigger rolling summary generation capturing: research objective, missions discussed, subsystems, answered findings, cited document IDs, and unresolved questions.
   - Inject summary into `query_rewriter.py` as context while ensuring original evidence chunks are always re-retrieved.
2. **Database Backup & Restore Script (P1):**
   - Provide `scripts/backup_db.py` and `scripts/restore_db.py` for Postgres + pgvector and storage directory snapshots.
3. **Ready & Health Endpoint Deepening (P1):**
   - Add `/api/ready` endpoint checking DB connection, pgvector extension, model cache readiness, and disk space.

### Phase P2: Advanced Intelligence & Scaling
1. **STAIR L3/L4 Fine-Tuning Readiness (P2):**
   - Verify `scripts/generate_training_data.py` outputs valid JSONL pairs from database leaf sections.
   - Document Colab/Kaggle execution steps in `docs/stair_training.md`.
2. **Full Playwright E2E Verification & Soak Test (P2):**
   - Execute Playwright test suite against live frontend and backend.
   - Execute 30-minute soak test simulating repeated queries and voice interactions.

---

## 4. Verification Evidence Log

### Test Suite Execution
- **Command:** `backend\.venv\Scripts\python.exe -m pytest backend/tests -v --tb=short`
- **Result:** `34 passed, 1 warning in 33.56s`
- **Coverage Highlights:**
  - `test_abstention_and_confidence.py`: 4 tests verifying exact abstention string and deterministic confidence levels.
  - `test_citation_validator.py`: 4 tests verifying valid citations, rejected page numbers, stripped ungrounded quotes, and fabricated chunk detection.
  - `test_ingestion_validation.py`: 4 tests verifying source URL/licence provenance, PDF magic bytes, SHA-256 dedupe, OCR quality check, and prompt injection sanitization.
  - `test_phase2_stair_and_toc.py`: 6 tests verifying multi-level ToC heuristics, LLM repair, BM25 ToC selection, STAIR L2 leaf ID validation, and L3 stub.
  - `test_phase3_voice_and_followup.py`: 4 tests verifying query rewriter, spoken formatter, typed vs spoken citation identity, and aerospace vocabulary prompt.
  - `test_phase4_failures.py`: 3 tests verifying evidence validator, reconstructor separation of chronology and causality, and quote overlap threshold.
  - `test_phase5_similar_and_kg.py`: 4 tests verifying problem entity extraction, subsystem boost, multi-hop KG query, and incident indexing.
  - `test_phase6_security_and_demo.py`: 5 tests verifying malicious PDF hardening, prompt injection defense, JWT/RBAC, sliding window rate limiting, and admin routes.
