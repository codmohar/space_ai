"""Rolling summarizer for long engineering conversations.

Preserves research objective, topic, missions, subsystems, answered questions/findings,
cited document IDs, and unresolved questions. Always used as contextual guidance only;
subsequent queries always re-retrieve original evidence chunks.
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.llm.client import LLMClient, get_llm_client

logger = logging.getLogger(__name__)


class RollingConversationSummary(BaseModel):
    research_objective: str = Field(..., description="Overall research goal of the user")
    missions: list[str] = Field(default_factory=list, description="Missions mentioned or scoped")
    subsystems: list[str] = Field(default_factory=list, description="Subsystems investigated")
    key_findings: list[str] = Field(default_factory=list, description="Key facts established with citations")
    cited_document_ids: list[str] = Field(default_factory=list, description="UUID strings or codes of cited docs")
    unresolved_questions: list[str] = Field(default_factory=list, description="Remaining open questions or ambiguities")
    formatted_summary: str = Field(..., description="Concise multi-line markdown summary for context injection")


def build_rolling_summary(
    messages: Sequence[tuple[str, str]],
    existing_summary: Optional[str] = None,
    mission_scope: Optional[str] = None,
    llm_client: Optional[LLMClient] = None,
) -> str:
    """Generate or update a rolling summary after multi-turn conversations."""
    if not messages:
        return existing_summary or ""

    transcript = "\n".join(f"{role.upper()}: {text[:600]}" for role, text in messages)

    system_prompt = (
        "You are an aerospace mission intelligence summarizer. Maintain a rolling structured summary of an "
        "engineering research dialogue. Capture: (1) Research objective, (2) Missions discussed, "
        "(3) Subsystems analyzed, (4) Established technical findings with citations, (5) Cited document references, "
        "(6) Unresolved questions. Format a clear, dense markdown summary. Do not fabricate facts."
    )
    user_prompt = (
        f"EXISTING SUMMARY:\n{existing_summary or 'None'}\n\n"
        f"MISSION SCOPE: {mission_scope or 'None'}\n\n"
        f"NEW CONVERSATION TURNS:\n{transcript}"
    )

    client = llm_client or get_llm_client()
    settings = get_settings()
    if llm_client is None and not settings.gemini_api_key:
        return _extractive_summary_fallback(messages, existing_summary, mission_scope)

    try:
        res = client.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_cls=RollingConversationSummary,
            max_retries=1,
        )
        return res.formatted_summary.strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM rolling summarizer failed, using extractive fallback: %s", exc)
        return _extractive_summary_fallback(messages, existing_summary, mission_scope)


def _extractive_summary_fallback(
    messages: Sequence[tuple[str, str]],
    existing_summary: Optional[str] = None,
    mission_scope: Optional[str] = None,
) -> str:
    user_queries = [text for role, text in messages if role == "user"]
    assistant_replies = [text for role, text in messages if role == "assistant"]

    summary_lines = []
    if mission_scope:
        summary_lines.append(f"**Mission Scope**: {mission_scope}")
    if user_queries:
        summary_lines.append(f"**Research Questions**: {'; '.join(user_queries[-3:])}")
    if assistant_replies:
        first_line = assistant_replies[-1].split("\n")[0][:150]
        summary_lines.append(f"**Latest Established Finding**: {first_line}")
    if existing_summary:
        summary_lines.append(f"**Prior Context**: {existing_summary[:200]}...")

    return "\n".join(summary_lines)
