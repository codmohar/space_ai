"""Deterministic retrieval confidence calculator (NEVER LLM self-reported)."""

from __future__ import annotations

from app.schemas import ConfidenceCategory


def compute_retrieval_confidence(
    top_rerank_score: float,
    mean_cited_rerank_score: float,
    citation_pass_rate: float,
    verified_claim_count: int,
    dropped_claim_count: int,
    has_conflicting_evidence: bool = False,
    min_rerank_threshold: float = 0.18,
) -> tuple[ConfidenceCategory, float]:
    """Compute confidence category and numeric score [0, 1] strictly from retrieval & verification signals."""
    if verified_claim_count == 0 or top_rerank_score <= 0.0:
        return "None", 0.0

    if top_rerank_score < min_rerank_threshold:
        return "Insufficient", round(min(0.25, top_rerank_score), 3)

    total_claims = verified_claim_count + dropped_claim_count
    claim_coverage = verified_claim_count / total_claims if total_claims > 0 else 0.0

    raw_score = (
        0.45 * min(1.0, max(0.0, top_rerank_score))
        + 0.25 * min(1.0, max(0.0, mean_cited_rerank_score))
        + 0.20 * min(1.0, max(0.0, citation_pass_rate))
        + 0.10 * min(1.0, max(0.0, claim_coverage))
    )
    score = round(min(1.0, max(0.0, raw_score)), 3)

    if has_conflicting_evidence:
        return "Conflicting", score

    if score >= 0.72 and citation_pass_rate >= 0.8 and dropped_claim_count == 0:
        return "Strong", score

    if score >= 0.38 and verified_claim_count >= 1:
        return "Partial", score

    return "Insufficient", score
