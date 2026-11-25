"""Similar Past Failures search service: entity/subsystem extraction + hybrid + rerank + boost."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from rank_bm25 import BM25Okapi
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.documents import Document, DocumentChunk, DocumentSection
from app.models.failure_kg import MissionIncident
from app.services.incidents.indexer import (
    MECHANISM_KEYWORDS,
    SUBSYSTEM_TAXONOMY,
)
from app.services.retrieval.embeddings import get_embedding_service
from app.services.retrieval.hybrid import get_reranker


def _tok(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:[-_/][a-z0-9]+)*", text.lower())


@dataclass
class ExtractedProblemProfile:
    subsystems: list[str]
    mechanisms: list[str]
    keywords: list[str]


@dataclass
class SimilarIncidentMatch:
    incident: MissionIncident
    doc: Document
    section_title: str
    bbox_json: list[dict]
    semantic_score: float
    keyword_score: float
    rerank_score: float
    subsystem_match_score: float
    matched_terms: list[str]
    total_relevance: float


def extract_problem_entities(problem_description: str) -> ExtractedProblemProfile:
    """Extract target aerospace subsystems, failure mechanisms, and technical terms from query."""
    lower = problem_description.lower()
    subsystems: list[str] = []
    matched_kws: list[str] = []

    for sub, kws in SUBSYSTEM_TAXONOMY.items():
        hits = [kw for kw in kws if kw in lower]
        if hits:
            subsystems.append(sub)
            matched_kws.extend(hits)

    mechanisms: list[str] = []
    for mech, kws in MECHANISM_KEYWORDS.items():
        hits = [kw for kw in kws if kw in lower]
        if hits:
            mechanisms.append(mech)
            matched_kws.extend(hits)

    return ExtractedProblemProfile(
        subsystems=subsystems,
        mechanisms=mechanisms,
        keywords=list(dict.fromkeys(matched_kws or _tok(problem_description)[:8])),
    )


def compute_subsystem_boost(
    profile: ExtractedProblemProfile,
    incident: MissionIncident,
) -> tuple[float, list[str]]:
    """Compute normalized [0, 1] subsystem & failure-mechanism match boost plus matched terms."""
    score = 0.0
    matched: list[str] = []
    inc_blob = (
        f"{incident.subsystem} {incident.component or ''} {incident.failure_mechanism or ''} "
        f"{incident.anomaly_title} {incident.anomaly_description} {incident.root_cause}"
    ).lower()

    if incident.subsystem in profile.subsystems:
        score += 0.55
        matched.append(incident.subsystem)

    if incident.failure_mechanism and incident.failure_mechanism in profile.mechanisms:
        score += 0.30
        matched.append(incident.failure_mechanism)

    kw_hits = [kw for kw in profile.keywords if kw in inc_blob]
    if kw_hits:
        score += min(0.35, 0.12 * len(kw_hits))
        matched.extend(kw_hits[:4])

    return round(min(1.0, score), 4), list(dict.fromkeys(matched))


class SimilarFailuresService:
    def search(
        self,
        db: Session,
        problem_description: str,
        top_k: int = 6,
        mission_filter: Optional[str] = None,
    ) -> tuple[ExtractedProblemProfile, list[SimilarIncidentMatch]]:
        profile = extract_problem_entities(problem_description)

        stmt = (
            select(MissionIncident, Document, DocumentChunk, DocumentSection)
            .join(Document, Document.id == MissionIncident.document_id)
            .join(DocumentChunk, DocumentChunk.id == MissionIncident.chunk_id)
            .outerjoin(DocumentSection, DocumentSection.id == MissionIncident.section_id)
        )
        if mission_filter:
            stmt = stmt.where(MissionIncident.mission == mission_filter)

        rows = db.execute(stmt).all()
        if not rows:
            return profile, []

        # 1. Semantic similarity via pgvector / cosine dot product
        embedder = get_embedding_service()
        q_vec = embedder.embed_query(problem_description)

        def _cosine(a: list[float] | None, b: list[float]) -> float:
            if not a:
                return 0.0
            return max(0.0, min(1.0, float(sum(x * y for x, y in zip(a, b, strict=False)))))

        semantic_scores = [_cosine(inc.embedding, q_vec) for inc, _d, _c, _s in rows]

        # 2. BM25 lexical similarity
        corpus_docs = [
            _tok(
                f"{inc.mission} {inc.subsystem} {inc.component or ''} {inc.anomaly_title} "
                f"{inc.anomaly_description} {inc.root_cause} {inc.corrective_action}"
            )
            for inc, _d, _c, _s in rows
        ]
        q_tokens = _tok(problem_description)
        raw_bm25 = (
            BM25Okapi(corpus_docs).get_scores(q_tokens)
            if q_tokens and any(corpus_docs)
            else [0.0] * len(rows)
        )
        max_bm25 = max((float(s) for s in raw_bm25), default=0.0)
        q_set = set(q_tokens)

        keyword_scores: list[float] = []
        for idx, b_val in enumerate(raw_bm25):
            overlap = len(q_set & set(corpus_docs[idx])) / max(1, len(q_set))
            norm_b = (max(0.0, float(b_val)) / max_bm25) if max_bm25 > 0 else 0.0
            keyword_scores.append(round(min(1.0, 0.7 * norm_b + 0.3 * overlap), 4))

        # Select candidate pool by combined semantic + keyword before cross-encoder reranking
        pre_ranked = sorted(
            range(len(rows)),
            key=lambda i: 0.6 * semantic_scores[i] + 0.4 * keyword_scores[i],
            reverse=True,
        )[:15]

        reranker = get_reranker()
        passages = [
            f"{rows[i][0].mission} | {rows[i][0].subsystem}: {rows[i][0].anomaly_title}. "
            f"{rows[i][0].anomaly_description} Root cause: {rows[i][0].root_cause}"
            for i in pre_ranked
        ]
        rerank_scores = reranker.score_pairs(problem_description, passages)

        matches: list[SimilarIncidentMatch] = []
        for idx, rerank_val in zip(pre_ranked, rerank_scores, strict=True):
            inc, doc, chunk, sec = rows[idx]
            sub_boost, matched_terms = compute_subsystem_boost(profile, inc)
            sem_val = round(semantic_scores[idx], 4)
            kw_val = keyword_scores[idx]

            # Transparent weighted combination: cross-encoder + semantic + keyword + subsystem boost
            total = round(
                min(
                    1.0,
                    0.45 * rerank_val + 0.20 * sem_val + 0.10 * kw_val + 0.25 * sub_boost,
                ),
                4,
            )
            matches.append(
                SimilarIncidentMatch(
                    incident=inc,
                    doc=doc,
                    section_title=sec.title if sec else "Document Body",
                    bbox_json=list(chunk.bbox_json or []),
                    semantic_score=sem_val,
                    keyword_score=kw_val,
                    rerank_score=rerank_val,
                    subsystem_match_score=sub_boost,
                    matched_terms=matched_terms,
                    total_relevance=total,
                )
            )

        matches.sort(key=lambda m: m.total_relevance, reverse=True)
        return profile, matches[:top_k]
