"""Pre-warmed, DB-verified Demo Mode cache and guided walkthrough orchestration."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.models.documents import Document, DocumentChunk
from app.schemas import ChatResponse, DemoStepOut
from app.services.llm.client import LLMClient
from app.services.rag.citation_validator import LLMCitationRef, LLMClaimItem, LLMRAGOutput
from app.services.rag.service import RAGService

T = TypeVar("T", bound=BaseModel)


class _OfflineExtractiveLLM(LLMClient):
    """Deterministic extractive fallback used ONLY if live LLM hits 503 during demo prewarm."""

    model_name = "extractive-fallback-v1"

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema_cls: Type[T],
        max_retries: int = 2,
    ) -> T:
        # Handle ToC section selection JSON when STAIR selector invokes LLM
        if "selected_section_ids" in schema_cls.model_fields:
            sec_ids = re.findall(
                r'"section_id"\s*:\s*"([0-9a-fA-F-]{36})"', user_prompt
            )
            if not sec_ids:
                sec_ids = re.findall(r"\b([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b", user_prompt)
            return schema_cls.model_validate(
                {"selected_section_ids": sec_ids[:3], "reason": "Extractive fallback selection"}
            )

        # Parse real <evidence_chunk ...> blocks delimited in user_prompt
        chunk_blocks = re.findall(
            r'<evidence_chunk\s+chunk_id="([0-9a-fA-F-]{36})"\s+document_id="([0-9a-fA-F-]{36})"[^>]*?page="(\d+)"[^>]*?>\s*(.*?)\s*</evidence_chunk>',
            user_prompt,
            flags=re.DOTALL,
        )
        claims: list[LLMClaimItem] = []
        for chunk_id, doc_id, page_str, body in chunk_blocks[:3]:
            sentences = [
                s.strip()
                for s in re.split(r"(?<=[.!?])\s+", body.strip())
                if len(s.strip()) >= 25
            ]
            if not sentences:
                snippet = body.strip()[:220]
            else:
                snippet = " ".join(sentences[:2])[:280]
            if len(snippet) < 8:
                continue
            claims.append(
                LLMClaimItem(
                    claim_text=snippet,
                    evidence_classification="explicitly_stated",
                    citation_refs=[
                        LLMCitationRef(
                            chunk_id=chunk_id,
                            document_id=doc_id,
                            page_number=int(page_str),
                            quote=snippet[:180],
                        )
                    ],
                )
            )
        rag_out = LLMRAGOutput(insufficient_evidence=len(claims) == 0, claims=claims)
        return schema_cls.model_validate(rag_out.model_dump())

CURATED_DEMO_QUERIES: list[dict[str, Optional[str]]] = [
    {
        "query": "What caused the thermal and oxygen tank failure during the Apollo 13 mission?",
        "mission": "Apollo 13",
    },
    {
        "query": "Why did the Mars Climate Orbiter lose attitude control and enter the Martian atmosphere too low?",
        "mission": "Mars Climate Orbiter",
    },
    {
        "query": "What software and touchdown sensor defect caused the Mars Polar Lander loss?",
        "mission": "Mars Polar Lander",
    },
    {
        "query": "What caused the ISS Columbus radiator valve failure in 2019?",
        "mission": None,
    },
]


def _normalize_key(query: str, mission: Optional[str]) -> str:
    return f"{(mission or 'ALL').strip().lower()}::{' '.join(query.strip().lower().split())}"


def _resolve_cache_path() -> Path:
    settings = get_settings()
    path = Path(settings.demo_cache_path)
    if not path.is_absolute():
        # Support running from repo root or /app (backend container)
        if Path("/data").exists() and str(path).startswith("../data"):
            return Path("/data/demo/demo_cache.json")
        return (Path.cwd() / path).resolve()
    return path


def load_demo_cache_raw() -> dict[str, Any]:
    path = _resolve_cache_path()
    if not path.exists():
        return {"generated_at": None, "entries": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"generated_at": None, "entries": {}}


def _verify_cached_citations(db: Session, response_dict: dict[str, Any]) -> bool:
    """Verify every cached citation chunk_id still resolves in PostgreSQL."""
    citations = response_dict.get("citations") or []
    for cit in citations:
        raw_id = cit.get("chunk_id")
        if not raw_id:
            return False
        try:
            cid = uuid.UUID(str(raw_id))
        except ValueError:
            return False
        if db.get(DocumentChunk, cid) is None:
            return False
    return True


def lookup_cached_demo_answer(
    db: Session,
    query: str,
    mission: Optional[str] = None,
) -> Optional[ChatResponse]:
    payload = load_demo_cache_raw()
    entries = payload.get("entries") or {}
    key = _normalize_key(query, mission)
    entry = entries.get(key)
    if entry is None:
        # Fallback match ignoring mission filter if query text matches identically
        q_norm = " ".join(query.strip().lower().split())
        for candidate in entries.values():
            if " ".join(candidate.get("query", "").strip().lower().split()) == q_norm:
                entry = candidate
                break
    if entry is None:
        return None

    resp_dict = entry.get("response")
    if not isinstance(resp_dict, dict):
        return None
    if not _verify_cached_citations(db, resp_dict):
        return None

    try:
        return ChatResponse.model_validate(resp_dict)
    except Exception:  # noqa: BLE001
        return None


def prewarm_demo_cache(db: Session) -> dict[str, Any]:
    """Run real RAGService over curated queries and persist DB-verified responses."""
    docs_present = db.execute(select(Document.id).limit(1)).scalar_one_or_none()
    if docs_present is None:
        return {"status": "skipped_empty_corpus", "cached_queries": 0, "generated_at": ""}

    # Also ensure embedding & reranker singletons are warmed in memory
    try:
        from app.services.retrieval.embeddings import get_embedding_model
        from app.services.retrieval.reranker import get_reranker_model

        get_embedding_model()
        get_reranker_model()
    except Exception:  # noqa: BLE001
        pass

    rag = RAGService()
    fallback_rag = RAGService(llm_client=_OfflineExtractiveLLM())
    entries: dict[str, Any] = {}
    fallback_used = 0
    for item in CURATED_DEMO_QUERIES:
        query = item["query"] or ""
        mission = item["mission"]
        try:
            resp = rag.chat_and_persist(
                db=db,
                query=query,
                request_id=f"demo-prewarm-{uuid.uuid4().hex[:8]}",
                mission=mission,
                selector_mode="auto",
            )
        except ApiError:
            fallback_used += 1
            resp = fallback_rag.chat_and_persist(
                db=db,
                query=query,
                request_id=f"demo-prewarm-fb-{uuid.uuid4().hex[:8]}",
                mission=mission,
                selector_mode="auto",
            )
        key = _normalize_key(query, mission)
        entries[key] = {
            "query": query,
            "mission": mission,
            "response": resp.model_dump(mode="json"),
        }

    generated_at = datetime.now(timezone.utc).isoformat()
    cache_payload = {
        "generated_at": generated_at,
        "fallback_used": fallback_used,
        "entries": entries,
    }
    path = _resolve_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache_payload, indent=2), encoding="utf-8")

    return {
        "status": "warmed",
        "cached_queries": len(entries),
        "generated_at": generated_at,
    }


def get_demo_walkthrough_steps(db: Session) -> list[DemoStepOut]:
    docs = db.execute(select(Document).order_by(Document.created_at.asc())).scalars().all()
    a13 = next((d for d in docs if "A13" in d.doc_code or "Apollo 13" in d.mission), docs[0] if docs else None)
    mco = next((d for d in docs if "MCO" in d.doc_code or "Climate Orbiter" in d.mission), docs[0] if docs else None)

    return [
        DemoStepOut(
            step_id="step-stair-rag",
            step_number=1,
            title="Thermal & Cryogenic Query via STAIR",
            subtitle="Route query through ToC leaf-section selection -> hybrid search -> cross-encoder -> citation validator.",
            target_page="chat",
            suggested_query="What caused the thermal and oxygen tank failure during the Apollo 13 mission?",
            suggested_mission=a13.mission if a13 else "Apollo 13",
            suggested_doc_code=a13.doc_code if a13 else "NASA-A13-1970",
            action_label="Run Cited Query",
            notes="Observe deterministic confidence meter, STAIR leaf sections, and evidence classification tags.",
        ),
        DemoStepOut(
            step_id="step-pdf-citation",
            step_number=2,
            title="Inspect PDF Evidence & BBox Highlight",
            subtitle="Jump to the exact cited page inside the public NASA report with bounding-box highlight and licence metadata.",
            target_page="citation",
            suggested_doc_code=a13.doc_code if a13 else "NASA-A13-1970",
            action_label="Open Citation Viewer",
            notes="Click any citation chip (e.g. [NASA-A13-1970 · p.xx]) to jump and inspect source provenance.",
        ),
        DemoStepOut(
            step_id="step-similar-failures",
            step_number=3,
            title="Cross-Mission Similar Failures",
            subtitle="Describe a thermal-control or propulsion anomaly and rank indexed incidents with subsystem-match breakdown.",
            target_page="similar",
            suggested_query="Cryogenic tank heater thermal switch overload and wiring insulation degradation",
            action_label="Search Similar Failures",
            notes="Shows semantic, lexical, rerank, and subsystem-match scores plus direct Reconstruct Chain trigger.",
        ),
        DemoStepOut(
            step_id="step-failure-chain",
            step_number=4,
            title="Verify Failure Chain Reconstruction",
            subtitle="Inspect chronological vs causal edges (caused_by / contributed_to) and pending/verified provenance.",
            target_page="failures",
            suggested_mission=mco.mission if mco else "Mars Climate Orbiter",
            suggested_doc_code=mco.doc_code if mco else "NASA-MCO-1999",
            action_label="Open Failure Chain",
            notes="Click any event node to inspect the verbatim evidence quote and jump straight to its PDF page.",
        ),
        DemoStepOut(
            step_id="step-knowledge-graph",
            step_number=5,
            title="Multi-Hop Engineering Knowledge Graph",
            subtitle="Query Mission -> Subsystem -> Component -> Anomaly -> Root Cause -> Corrective Action across reports.",
            target_page="kg",
            suggested_query="missions with propulsion anomalies and their corrective actions",
            action_label="Query Knowledge Graph",
            notes="Every graph path resolves back to a verified source chunk and page number.",
        ),
        DemoStepOut(
            step_id="step-eval-admin",
            step_number=6,
            title="Measured Benchmarks & Audit Telemetry",
            subtitle="Review real /scripts evaluation metrics, prompt/model version logs, RBAC roles, and security audit trail.",
            target_page="eval",
            action_label="Inspect Evaluation & Admin",
            notes="Never displays fabricated scores; shows measured outputs from scripts/evaluate_retrieval.py.",
        ),
    ]
