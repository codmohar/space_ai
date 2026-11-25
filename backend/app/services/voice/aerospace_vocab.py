"""Aerospace vocabulary prompt builder for faster-whisper STT."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.documents import Document

CORE_AEROSPACE_TERMS = [
    "Mars Climate Orbiter",
    "Mars Polar Lander",
    "Apollo 13",
    "Deep Space 2",
    "Hubble Space Telescope",
    "Space Shuttle Challenger",
    "Space Shuttle Columbia",
    "Chandrayaan",
    "ISRO",
    "NASA",
    "ESA",
    "Small Forces",
    "Newton-seconds",
    "pound-seconds",
    "Angular Momentum Desaturation",
    "periapsis",
    "Trajectory Correction Maneuver",
    "Software Interface Specification",
    "cryogenic oxygen tank",
    "Service Module",
    "Lunar Module",
    "Hall effect",
    "entry, descent, and landing",
    "Reaction Control System",
    "thermostatic switches",
    "spherical aberration",
    "Reflective Null Corrector",
]


def build_aerospace_vocab_prompt(db: Optional[Session] = None) -> str:
    """Build Whisper initial_prompt biased toward ingested missions & spacecraft subsystems."""
    terms = list(CORE_AEROSPACE_TERMS)
    if db is not None:
        try:
            docs = db.execute(select(Document.mission, Document.doc_code, Document.org)).all()
            for mission, doc_code, org in docs:
                for val in (mission, doc_code, org):
                    if val and val not in terms:
                        terms.append(val)
        except Exception:  # noqa: BLE001
            pass

    return (
        "Spacecraft mission engineering telemetry and failure investigation terms: "
        + ", ".join(terms[:45])
        + "."
    )
