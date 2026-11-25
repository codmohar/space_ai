"""Upload validation, hashing, and prompt-injection text sanitization."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable

from app.core.errors import ApiError

ALLOWED_PDF_MIMES = {"application/pdf", "application/x-pdf", "application/octet-stream"}
PDF_MAGIC_BYTES = b"%PDF-"

_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)ignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|above|prior)\s+instructions?"),
    re.compile(r"(?i)disregard\s+(?:all\s+|the\s+)?(?:system|previous)\s+(?:prompt|instructions?)"),
    re.compile(r"(?i)you\s+are\s+now\s+(?:a|an|in)\s+(?:developer|jailbreak|unrestricted)\s+mode"),
    re.compile(r"(?i)<\s*/?\s*(?:system|instruction|prompt|evidence_chunk)\s*>"),
)


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_pdf_bytes(
    data: bytes,
    filename: str,
    content_type: str | None = None,
    max_upload_mb: int = 100,
) -> str:
    if not data:
        raise ApiError("EMPTY_FILE", "Uploaded PDF file is empty.", status_code=400)

    max_bytes = max_upload_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise ApiError(
            "FILE_TOO_LARGE",
            f"File exceeds maximum allowed size of {max_upload_mb} MB.",
            status_code=413,
            details={"size_bytes": len(data), "max_bytes": max_bytes},
        )

    if not filename.lower().endswith(".pdf"):
        raise ApiError("INVALID_EXTENSION", "Only .pdf files are accepted.", status_code=400)

    if content_type and content_type.lower() not in ALLOWED_PDF_MIMES:
        raise ApiError(
            "INVALID_MIME_TYPE",
            f"Unsupported MIME type: {content_type}. Expected application/pdf.",
            status_code=415,
        )

    if not data[:8].lstrip().startswith(PDF_MAGIC_BYTES):
        raise ApiError(
            "INVALID_MAGIC_BYTES",
            "File does not begin with valid %PDF- magic bytes.",
            status_code=400,
        )

    return compute_sha256(data)


def validate_provenance_fields(source_url: str, licence: str) -> tuple[str, str]:
    clean_url = (source_url or "").strip()
    clean_licence = (licence or "").strip()
    if not clean_url or not (clean_url.startswith("http://") or clean_url.startswith("https://")):
        raise ApiError(
            "MISSING_OR_INVALID_SOURCE_URL",
            "A valid public http(s) source_url is required for every document.",
            status_code=400,
        )
    if not clean_licence:
        raise ApiError(
            "MISSING_LICENCE",
            "Document licence is required (public documents only).",
            status_code=400,
        )
    return clean_url, clean_licence


def sanitize_untrusted_document_text(text: str) -> str:
    """Strip common prompt-injection directives from archival document text."""
    cleaned = text
    for pattern in _INJECTION_PATTERNS:
        cleaned = pattern.sub("[REDACTED_DIRECTIVE]", cleaned)
    return cleaned


def safe_filename(name: str, fallback: str = "document.pdf") -> str:
    stem = Path(name).name
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")
    return sanitized or fallback


def validate_required_columns(values: Iterable[str]) -> bool:
    return all(bool(v and v.strip()) for v in values)
