"""Conversation-memory follow-up query rewriter shared by text and voice."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal, Optional, Sequence

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.llm.client import LLMClient, get_llm_client

logger = logging.getLogger(__name__)

ResponseStyle = Literal["standard", "simpler"]

_SIMPLER_PATTERN = re.compile(
    r"\b(simpler|simple|plain\s+english|layman|eli5|easier|short(?:er)?|briefly)\b",
    re.IGNORECASE,
)
_FOLLOWUP_ANAPHORA = re.compile(
    r"\b(it|its|that|this|they|them|those|initial\s+issue|earlier|above|previous|more\s+detail|why\s+did|what\s+happened)\b",
    re.IGNORECASE,
)
_KNOWN_MISSIONS = (
    "Mars Climate Orbiter",
    "Mars Polar Lander",
    "Apollo 13",
    "Deep Space 2",
    "Hubble",
    "Challenger",
    "Columbia",
)


@dataclass
class RewriteResult:
    original_query: str
    standalone_query: str
    resolved_mission: Optional[str]
    response_style: ResponseStyle
    was_rewritten: bool


class _LLMQueryRewrite(BaseModel):
    standalone_query: str = Field(..., min_length=3, max_length=1000)
    resolved_mission: Optional[str] = None
    response_style: ResponseStyle = "standard"


def detect_response_style(query: str) -> ResponseStyle:
    return "simpler" if _SIMPLER_PATTERN.search(query) else "standard"


def _extract_mission_from_text(text: str) -> Optional[str]:
    lower = text.lower()
    for mission in _KNOWN_MISSIONS:
        if mission.lower() in lower:
            return mission
    return None


def _needs_rewrite(query: str, history: Sequence[tuple[str, str]]) -> bool:
    if not history:
        return False
    stripped = query.strip()
    if _SIMPLER_PATTERN.search(stripped):
        return True
    if _FOLLOWUP_ANAPHORA.search(stripped):
        return True
    # Short queries in an active conversation are typically follow-ups
    if len(stripped.split()) <= 8 and not _extract_mission_from_text(stripped):
        return True
    return False


def _deterministic_rewrite(
    query: str,
    history: Sequence[tuple[str, str]],
    mission_scope: Optional[str],
    style: ResponseStyle,
) -> RewriteResult:
    last_user_queries = [content for role, content in history if role == "user"]
    anchor = last_user_queries[-1].strip() if last_user_queries else ""

    inferred_mission = mission_scope or _extract_mission_from_text(query)
    if not inferred_mission:
        for _role, content in reversed(history):
            inferred_mission = _extract_mission_from_text(content)
            if inferred_mission:
                break

    if style == "simpler" and len(query.split()) <= 6 and anchor:
        standalone = anchor
    elif anchor and query.strip().lower() != anchor.lower():
        if inferred_mission and inferred_mission.lower() not in query.lower():
            standalone = f"Regarding {inferred_mission} ({anchor}): {query.strip()}"
        else:
            standalone = f"In the context of '{anchor}': {query.strip()}"
    else:
        standalone = query.strip()

    return RewriteResult(
        original_query=query.strip(),
        standalone_query=standalone,
        resolved_mission=inferred_mission,
        response_style=style,
        was_rewritten=standalone != query.strip(),
    )


def rewrite_followup_query(
    query: str,
    history: Sequence[tuple[str, str]],
    mission_scope: Optional[str] = None,
    llm_client: Optional[LLMClient] = None,
) -> RewriteResult:
    """Resolve follow-up queries ('what was the initial issue?', 'explain simpler') into a standalone question."""
    clean_query = query.strip()
    style = detect_response_style(clean_query)

    if not _needs_rewrite(clean_query, history):
        return RewriteResult(
            original_query=clean_query,
            standalone_query=clean_query,
            resolved_mission=mission_scope or _extract_mission_from_text(clean_query),
            response_style=style,
            was_rewritten=False,
        )

    settings = get_settings()
    if llm_client is None and not settings.gemini_api_key:
        return _deterministic_rewrite(clean_query, history, mission_scope, style)

    client = llm_client or get_llm_client()
    recent = history[-6:]
    transcript = "\n".join(f"{role.upper()}: {text[:500]}" for role, text in recent)

    system_prompt = (
        "You rewrite a conversational follow-up question into a completely self-contained, standalone "
        "engineering question for document retrieval. Resolve pronouns ('it', 'that', 'the initial issue') "
        "using the conversation history. If the user asks to 'explain simpler' or 'briefly', preserve the "
        "underlying factual topic in standalone_query and set response_style='simpler'. Do not answer the question."
    )
    user_prompt = (
        f"ACTIVE MISSION FILTER: {mission_scope or 'None'}\n\n"
        f"RECENT CONVERSATION:\n{transcript}\n\n"
        f"CURRENT FOLLOW-UP QUERY:\n{clean_query}"
    )

    try:
        out = client.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_cls=_LLMQueryRewrite,
            max_retries=1,
        )
        final_style: ResponseStyle = "simpler" if style == "simpler" else out.response_style
        return RewriteResult(
            original_query=clean_query,
            standalone_query=out.standalone_query.strip(),
            resolved_mission=mission_scope or out.resolved_mission or _extract_mission_from_text(out.standalone_query),
            response_style=final_style,
            was_rewritten=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM query rewriter failed, using deterministic fallback: %s", exc)
        return _deterministic_rewrite(clean_query, history, mission_scope, style)
