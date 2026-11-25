"""SectionSelector interface for STAIR-style structure-aware retrieval.

Honest STAIR levels (per GEMINI.md Rule 8):
- L1 (Phase 1): Hierarchical section index built during ingestion; pass-through selector.
- L2 (Phase 2): ToC-aware query-to-leaf selection (STAIR-inspired).
- L3/L4 (Phase 3+): Fine-tuned LoRA selector + constrained decoding.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Optional

from sqlalchemy.orm import Session


class SectionSelector(ABC):
    stair_level: str = "L1"

    @abstractmethod
    def select_sections(
        self,
        db: Session,
        query: str,
        document_ids: Optional[list[uuid.UUID]] = None,
        top_k_sections: int = 8,
    ) -> Optional[list[uuid.UUID]]:
        """Return selected leaf section UUIDs, or None for full-document search."""


class L1PassThroughSectionSelector(SectionSelector):
    """Phase 1 L1 selector: uses L1 hierarchical index metadata without leaf pruning."""

    stair_level: str = "L1"

    def select_sections(
        self,
        db: Session,
        query: str,
        document_ids: Optional[list[uuid.UUID]] = None,
        top_k_sections: int = 8,
    ) -> Optional[list[uuid.UUID]]:
        return None
