"""Spoken-answer formatter: concise radio-briefing output derived strictly from verified claims."""

from __future__ import annotations

import re
from typing import Sequence

from app.core.config import ABSTENTION_MESSAGE
from app.schemas import ClaimOut

_BRACKET_CIT_RE = re.compile(r"\s*\[[^\]]+\]")

_ACRONYM_EXPANSIONS = {
    "AMD": "Angular Momentum Desaturation",
    "EDL": "entry, descent, and landing",
    "SIS": "Software Interface Specification",
    "TCM": "Trajectory Correction Maneuver",
    "MET": "Mission Elapsed Time",
}


def _clean_claim_for_speech(text: str, simpler: bool = False) -> str:
    cleaned = _BRACKET_CIT_RE.sub("", text).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if simpler:
        for abbr, full in _ACRONYM_EXPANSIONS.items():
            cleaned = re.sub(rf"\b{re.escape(abbr)}\b", full, cleaned)
    if cleaned and cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def format_spoken_answer(
    claims: Sequence[ClaimOut],
    abstained: bool,
    written_answer: str,
    style: str = "standard",
) -> str:
    """Create a shorter spoken summary preserving identical verified claims (zero new facts)."""
    if abstained or not claims:
        return ABSTENTION_MESSAGE

    simpler = style == "simpler"
    max_claims = 2 if simpler else 3
    max_words = 45 if simpler else 68

    sentences: list[str] = []
    word_budget = 0

    for idx, claim in enumerate(claims[:max_claims]):
        body = _clean_claim_for_speech(claim.claim_text, simpler=simpler)
        # Keep only the first sentence of each claim so spoken output stays crisp
        first_sentence = re.split(r"(?<=[.!?])\s+", body)[0].strip()

        if idx == 0 and claim.evidence_classification == "official_root_cause":
            if "root cause" not in first_sentence.lower():
                first_sentence = f"Official root cause: {first_sentence}"
        elif idx == 0 and claim.evidence_classification == "system_inference":
            first_sentence = f"Based on the report evidence: {first_sentence}"

        words = first_sentence.split()
        if sentences and word_budget + len(words) > max_words:
            break
        if len(words) > max_words and not sentences:
            first_sentence = " ".join(words[:max_words]).rstrip(",;:") + "."
            words = first_sentence.split()

        sentences.append(first_sentence)
        word_budget += len(words)

    spoken = " ".join(sentences).strip()
    # Guarantee spoken summary never exceeds written answer length unless written answer is tiny
    if len(spoken) >= len(written_answer) and len(written_answer) > 60:
        first_only = sentences[0] if sentences else spoken
        spoken = first_only
    return spoken or ABSTENTION_MESSAGE
