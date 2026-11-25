# MISSIONWISE AI — Phase 1 Architecture

## 1. Monorepo Layout
- `backend/`: FastAPI service, SQLAlchemy 2 models, Alembic migrations, PyMuPDF/Tesseract ingestion, hybrid retrieval, grounded RAG, citation validator, and pytest suite.
- `frontend/`: React + Vite + TypeScript mission-control console, design tokens, app shell, Research Assistant, and PDF bbox Citation Viewer.
- `data/raw_documents/`: Public NASA/ISRO/ESA PDFs and `manifest.json` (provenance metadata).
- `data/evaluation/`: Reserved for Phase 2+ human-reviewed ground-truth evaluation datasets.
- `scripts/`: Download and CLI ingestion utilities.

## 2. Single Shared Retrieval & Citation Pipeline
All query surfaces (`/api/chat` in Phase 1; voice, failure chain extraction, and similar-failures in Phase 2+) call `RAGService` (`backend/app/services/rag/service.py`), which executes:
1. Query normalization & mission/document scoping
2. `SectionSelector` hook (Phase 1 L1 pass-through; Phase 2 STAIR L2 ToC-to-leaf)
3. Dense vector search (pgvector HNSW) + BM25 lexical search -> RRF merge -> Cross-Encoder reranker
4. Evidence sufficiency threshold check
5. Prompt-injection-guarded LLM generation (`LLMClient`)
6. Deterministic `CitationValidator` & `ConfidenceCalculator`
7. Full stage logging to `retrieval_logs`

## 3. Non-Negotiable Grounding Guarantees
- Every factual claim maps to `{document_title, page_number, section, chunk_id, source_url}`.
- Unresolved or unsupported citations are stripped before returning; if no verified claims remain, the service abstains with:
  `"Not found in the available mission reports. More supporting documentation is required."`
- Evaluation metrics are never fabricated; Phase 1 Dashboard displays `"Not yet evaluated"` until `/scripts` evaluation benchmarks run in Phase 2+.
