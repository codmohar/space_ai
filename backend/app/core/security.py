"""Upload validation, hashing, and prompt-injection text sanitization."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable

import fitz

from app.core.errors import ApiError

ALLOWED_PDF_MIMES = {"application/pdf", "application/x-pdf", "application/octet-stream"}
PDF_MAGIC_BYTES = b"%PDF-"
ZIP_MAGIC_BYTES = b"PK\x03\x04"
PNG_MAGIC_BYTES = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC_BYTES = b"\xff\xd8\xff"
TIFF_LE_MAGIC = b"II*\x00"
TIFF_BE_MAGIC = b"MM\x00*"

SUPPORTED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
    ".csv": "text/csv",
    ".xml": "application/xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}

_DANGEROUS_PDF_OBJECTS = (b"/JavaScript", b"/JS ", b"/JS\n", b"/JS\r", b"/Launch", b"/OpenAction")

_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)ignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|above|prior)\s+instructions?"),
    re.compile(r"(?i)disregard\s+(?:all\s+|the\s+)?(?:system|previous)\s+(?:prompt|instructions?)"),
    re.compile(r"(?i)you\s+are\s+now\s+(?:a|an|in)\s+(?:developer|jailbreak|unrestricted)\s+mode"),
    re.compile(r"(?i)<\s*/?\s*(?:system|instruction|prompt|evidence_chunk|assistant|user)\s*>"),
    re.compile(r"(?i)(?:override|bypass)\s+(?:citation|safety|verification|grounding)\s+(?:rules?|checks?)"),
    re.compile(r"(?i)(?:fabricate|invent|fake)\s+(?:a\s+)?(?:citation|page\s+number|root\s+cause)"),
    re.compile(r"(?i)system\s*prompt\s*:\s*"),
    re.compile(r"(?i)act\s+as\s+(?:root|admin|system)\b"),
)


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_pdf_bytes(
    data: bytes,
    filename: str,
    content_type: str | None = None,
    max_upload_mb: int = 100,
    max_upload_pages: int = 800,
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

    for marker in _DANGEROUS_PDF_OBJECTS:
        if marker in data:
            raise ApiError(
                "ACTIVE_PDF_CONTENT_BLOCKED",
                "Uploaded PDF contains active scripting or launch actions that are blocked by security policy.",
                status_code=400,
                details={"marker": marker.decode("ascii", errors="ignore").strip()},
            )

    try:
        with fitz.open(stream=data, filetype="pdf") as pdf_doc:
            page_count = pdf_doc.page_count
    except Exception as exc:
        raise ApiError(
            "CORRUPT_PDF",
            "Uploaded file could not be parsed as a valid PDF document.",
            status_code=400,
            details={"reason": str(exc)},
        ) from exc

    if page_count <= 0:
        raise ApiError("EMPTY_PDF_PAGES", "Uploaded PDF contains zero pages.", status_code=400)
    if page_count > max_upload_pages:
        raise ApiError(
            "PDF_TOO_MANY_PAGES",
            f"PDF exceeds maximum allowed page limit ({max_upload_pages} pages).",
            status_code=413,
            details={"page_count": page_count, "max_pages": max_upload_pages},
        )

    return compute_sha256(data)


def validate_upload_bytes(
    data: bytes,
    filename: str,
    content_type: str | None = None,
    max_upload_mb: int = 100,
    max_upload_pages: int = 800,
) -> str:
    """Universal upload validator for multi-format documents (PDF, DOCX, PPTX, TXT, MD, HTML, CSV, XLSX, XML, Images)."""
    if not data:
        raise ApiError("EMPTY_FILE", "Uploaded file is empty.", status_code=400)

    max_bytes = max_upload_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise ApiError(
            "FILE_TOO_LARGE",
            f"File exceeds maximum allowed size of {max_upload_mb} MB.",
            status_code=413,
            details={"size_bytes": len(data), "max_bytes": max_bytes},
        )

    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ApiError(
            "INVALID_EXTENSION",
            f"Unsupported file format '{ext}'. Supported extensions: {', '.join(sorted(SUPPORTED_EXTENSIONS.keys()))}",
            status_code=400,
        )

    if ext == ".pdf":
        return validate_pdf_bytes(
            data=data,
            filename=filename,
            content_type=content_type,
            max_upload_mb=max_upload_mb,
            max_upload_pages=max_upload_pages,
        )

    if ext in (".docx", ".pptx", ".xlsx"):
        if not data.startswith(ZIP_MAGIC_BYTES):
            raise ApiError(
                "INVALID_MAGIC_BYTES",
                f"File '{filename}' lacks valid Office OpenXML (PK) magic bytes.",
                status_code=400,
            )
        # Zip-bomb protection: verify total uncompressed size <= max_bytes
        import zipfile
        from io import BytesIO

        try:
            with zipfile.ZipFile(BytesIO(data)) as zf:
                uncompressed_total = sum(zinfo.file_size for zinfo in zf.infolist())
                if uncompressed_total > max_bytes * 2:
                    raise ApiError(
                        "ZIP_BOMB_DETECTED",
                        "Decompressed size of archive exceeds security threshold.",
                        status_code=413,
                    )
        except zipfile.BadZipFile as exc:
            raise ApiError(
                "CORRUPT_DOCUMENT",
                f"File '{filename}' is corrupted or not a valid archive.",
                status_code=400,
            ) from exc

    elif ext == ".png":
        if not data.startswith(PNG_MAGIC_BYTES):
            raise ApiError("INVALID_MAGIC_BYTES", "File does not begin with valid PNG magic bytes.", status_code=400)
    elif ext in (".jpg", ".jpeg"):
        if not data.startswith(JPEG_MAGIC_BYTES):
            raise ApiError("INVALID_MAGIC_BYTES", "File does not begin with valid JPEG magic bytes.", status_code=400)
    elif ext in (".tiff", ".tif"):
        if not (data.startswith(TIFF_LE_MAGIC) or data.startswith(TIFF_BE_MAGIC)):
            raise ApiError("INVALID_MAGIC_BYTES", "File does not begin with valid TIFF magic bytes.", status_code=400)
    elif ext == ".xml":
        if b"<!ENTITY" in data or b"SYSTEM" in data:
            raise ApiError(
                "XML_ENTITY_INJECTION_BLOCKED",
                "XML documents containing DTD entity declarations are prohibited.",
                status_code=400,
            )
    elif ext in (".txt", ".md", ".html", ".htm", ".csv"):
        if b"\x00" in data[:1024]:
            raise ApiError("BINARY_IN_TEXT_FILE", "Text file contains illegal binary/null characters.", status_code=400)

    return compute_sha256(data)


def validate_provenance_fields(
    source_url: str,
    licence: str,
    allow_empty_url_as_uploaded: bool = False,
) -> tuple[str, str]:
    clean_url = (source_url or "").strip()
    clean_licence = (licence or "").strip()

    if not clean_licence:
        raise ApiError("MISSING_LICENCE", "Document licence is required.", status_code=400)

    if not clean_url:
        if allow_empty_url_as_uploaded:
            clean_url = "uploaded, no public URL"
        else:
            raise ApiError(
                "MISSING_OR_INVALID_SOURCE_URL",
                "A valid public http(s) source_url is required (or 'uploaded, no public URL').",
                status_code=400,
            )
    elif not (clean_url.startswith("http://") or clean_url.startswith("https://") or clean_url in ("uploaded, no public URL", "internal")):
        raise ApiError(
            "MISSING_OR_INVALID_SOURCE_URL",
            "A valid public http(s) source_url is required (or 'uploaded, no public URL').",
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
