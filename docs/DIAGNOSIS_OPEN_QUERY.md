# MISSIONWISE AI — Open Query & Corpus Diagnostics Report
**AVISHKAR 2K26 (Problem #10) — Team ProtoGuys**  
**Author**: Principal Engineer (RAG / IR / Full-Stack)  
**Date**: November 26, 2026  
**Git Branch**: `feature/doc-upload-open-query`  
**Checkpoint Commit**: `ffcf975`  

---

## 1. Executive Summary

A comprehensive investigation of the MISSIONWISE AI codebase was conducted across frontend and backend services to determine why free-form/open queries yielded brittle results or failed compared to curated demo inquiries.

### Primary Diagnosed Root Causes

1. **Strict Leaf-Section Hard-Filter without Global Safety Net (`backend/app/services/retrieval/hybrid.py:143`)**:
   - When STAIR (`BM25ToCSectionSelector` or `STAIRInspiredSectionSelector`) selected top-K leaf sections, the dense vector query (`DocumentChunk.section_id.in_(selected_section_ids)`) and BM25 candidate queries **strictly filtered** chunks solely to those section IDs.
   - For open queries that used phrasing differing slightly from formal ToC section titles (e.g., informal technical terminology, multi-hop mechanisms, or cross-document concepts), if the section selector picked sub-optimal leaf sections, **all relevant chunks across the rest of the corpus were completely hidden**.
   - **Fix Required**: As mandated by Step 2.4, execute retrieval within selected leaf sections **AND** a parallel global vector/BM25 pass across the entire corpus as a safety net, fused via Reciprocal Rank Fusion (RRF).

2. **In-Memory Hardcoded Mission List in Query Rewriting (`backend/app/services/rag/query_rewriter.py:27`)**:
   - `_KNOWN_MISSIONS = ("Mars Climate Orbiter", "Mars Polar Lander", "Apollo 13", "Deep Space 2", "Hubble", "Challenger", "Columbia")` was a hardcoded static tuple.
   - New missions from newly uploaded documents (e.g., Chandrayaan, Gaganyaan, Rosetta) were not recognized by heuristic mission extraction or follow-up query rewriting.
   - **Fix Required**: Dynamically query `SELECT DISTINCT mission FROM documents` or accept dynamic mission scopes from the active database session.

3. **Missing Frontend Ingestion Trigger on Document Explorer**:
   - While backend endpoints existed for upload and async processing (`/api/documents/upload/async`, `/api/documents/jobs/{job_id}`), the Document Explorer UI lacked a dedicated "Add Document" modal with multi-file picker, metadata overrides, physical progress polling, and duplicate detection.

4. **Incident Search Restrained to Pre-Indexed Incidents**:
   - `/api/similar-failures/search` only searched pre-populated rows in `mission_incidents`.
   - When newly uploaded PDFs were added, their anomalies were not yet in the structured incident table, preventing them from matching new design ideas.
   - **Fix Required**: Hybrid incident search over `mission_incidents` **AND** on-demand extraction from raw retrieved document chunks for newly added documents.

5. **Static Corpus Versioning for Cache Invalidation**:
   - The query path lacked an atomic `corpus_version` counter in Postgres/Redis to track incremental additions and invalidate stale caches immediately.

---

## 2. Detailed Findings Against Audit Checklist

### a) Hard-Coded Query Maps / Intent Switches / Canned Answers
- **Scan Result**: Negative for core chat and RAG pipeline.
- The standard `/api/chat` route executes `RAGService.answer_query` with actual vector search and cross-encoder reranking.
- The `demo_cache.py` module exists exclusively under `/api/demo/` for offline/fallback demo walkthroughs, but the primary `/api/chat` endpoint does not intercept or return mock canned answers.
- In `query_rewriter.py`, `_KNOWN_MISSIONS` was hardcoded; this will be made dynamic.

### b) Vector Store and Relational DB Execution
- **Scan Result**: Fully verified.
- `DocumentEmbedding.embedding.cosine_distance(query_vec)` executes real pgvector HNSW cosine distance queries against PostgreSQL 16.
- All original document text and chunk spans reside in the relational database table `document_chunks`.

### c) STAIR Section Selector Scope
- **File**: `backend/app/services/retrieval/section_selector.py`
- Operates dynamically on `DocumentSection` rows.
- **Vulnerability**: If `selected_section_ids` is non-empty, `HybridRetriever` applied a hard `WHERE section_id IN (...)` constraint. An open query whose answer resided in an adjacent section was completely filtered out before vector or BM25 scoring could evaluate it.

### d) Ingestion Indexing Scope
- Ingestion pipeline in `backend/app/services/ingestion/pipeline.py` correctly generates chunks, calculates `sentence-transformers` embeddings, and writes Postgres FTS `tsv` vector data.
- However, newly uploaded documents require immediate registration without server restarts.

### e) BM25 Index Structure
- `HybridRetriever` uses PostgreSQL full-text search (`websearch_to_tsquery('english', query)`) to select candidate chunks, followed by dynamic `BM25Okapi` re-scoring over candidate tokens in memory.
- Because candidate generation reads directly from `document_chunks.tsv`, any newly committed document is immediately searchable via BM25 without rebuilding in-memory global indexes.

### f) LLM Grounding vs. Background Knowledge
- Grounded prompts in `prompt_guard.py` explicitly instruct the model to answer exclusively from delimited `<evidence_chunk>` tags.
- Extractive fallback ensures that even when Gemini API quota limits (429) occur, verbatim claims are drawn strictly from retrieved chunk text with valid chunk IDs and page numbers.

---

## 3. Implementation Roadmap

1. **Step 1 (Add Document Feature)**:
   - Implement `AddDocumentModal` in frontend `DocumentsPage.tsx` with drag-and-drop, metadata inputs, upload validation, and job polling.
   - Enhance backend upload pipeline to update atomic corpus version and guarantee zero-restart searchability.
   - Implement `scripts/ingest_folder.py` for idempotent bulk loading.

2. **Step 2 (Open-Query RAG & Corpus-Wide STAIR)**:
   - Dynamic mission discovery from database in `query_rewriter.py`.
   - Implement dual-pass retrieval in `HybridRetriever`: (A) Leaf sections from STAIR, plus (B) Global corpus-wide dense & BM25 pass, fused via RRF.
   - Add "Why this answer?" diagnostics drawer to the UI.
   - Implement `corpus_version` tracking.

3. **Step 3 (Similar Past Failures for Engineering Ideas)**:
   - Support engineering idea descriptions with risk hypotheses generation.
   - Hybrid retrieval across both `mission_incidents` and raw chunks of newly ingested documents.
   - Structured risk cards with relevance breakdown and direct "Reconstruct failure chain" handoff.
