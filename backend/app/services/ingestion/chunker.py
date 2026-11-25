"""Structure- and page-preserving semantic chunker with bbox retention."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.services.ingestion.pdf_extractor import ExtractedDocument, ExtractedSection


@dataclass
class ChunkDraft:
    chunk_index: int
    page_number: int
    section_temp_id: int
    section_title: str
    section_path: str
    text: str
    token_count: int
    bbox_json: list[dict[str, Any]]
    ocr_used: bool
    ocr_confidence: float | None
    metadata_json: dict[str, Any]


def _estimate_tokens(text: str) -> int:
    # Approximate subword count (~1.3x whitespace words)
    words = len(text.split())
    return max(1, int(words * 1.3))


def _resolve_section_for_page(
    sections: list[ExtractedSection], page_number: int
) -> ExtractedSection:
    candidates = [
        s for s in sections if s.page_start <= page_number <= s.page_end
    ]
    if not candidates:
        candidates = [s for s in sections if s.page_start <= page_number]
    if not candidates:
        return sections[0]
    # Prefer deepest / latest matching leaf section
    leaf_candidates = [s for s in candidates if s.is_leaf]
    pool = leaf_candidates or candidates
    return max(pool, key=lambda s: (s.level, s.order_index))


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def chunk_extracted_document(
    extracted: ExtractedDocument,
    max_tokens: int = 380,
    overlap_tokens: int = 45,
) -> list[ChunkDraft]:
    """Group page blocks into semantically coherent chunks preserving section, page, and bboxes."""
    chunks: list[ChunkDraft] = []
    chunk_idx = 0

    for page in extracted.pages:
        if not page.blocks:
            continue
        section = _resolve_section_for_page(extracted.sections, page.page_number)

        buf_texts: list[str] = []
        buf_bboxes: list[dict[str, Any]] = []
        buf_tokens = 0
        buf_ocr_used = page.ocr_used
        buf_ocr_conf = page.ocr_confidence

        def flush_buffer() -> None:
            nonlocal chunk_idx, buf_texts, buf_bboxes, buf_tokens
            if not buf_texts:
                return
            joined = "\n\n".join(buf_texts).strip()
            if not joined:
                buf_texts, buf_bboxes, buf_tokens = [], [], 0
                return
            chunks.append(
                ChunkDraft(
                    chunk_index=chunk_idx,
                    page_number=page.page_number,
                    section_temp_id=section.temp_id,
                    section_title=section.title,
                    section_path=section.section_path,
                    text=joined,
                    token_count=_estimate_tokens(joined),
                    bbox_json=list(buf_bboxes),
                    ocr_used=buf_ocr_used,
                    ocr_confidence=buf_ocr_conf,
                    metadata_json={
                        "section_title": section.title,
                        "section_path": section.section_path,
                        "ocr_low_quality": page.ocr_low_quality,
                    },
                )
            )
            chunk_idx += 1

            # Retain last sentence as overlap if buffer had multiple blocks/sentences
            overlap_text = ""
            if len(buf_texts) > 1:
                sentences = _split_sentences(buf_texts[-1])
                if sentences and _estimate_tokens(sentences[-1]) <= overlap_tokens:
                    overlap_text = sentences[-1]
            if overlap_text:
                last_bbox = buf_bboxes[-1:]
                buf_texts = [overlap_text]
                buf_bboxes = last_bbox
                buf_tokens = _estimate_tokens(overlap_text)
            else:
                buf_texts, buf_bboxes, buf_tokens = [], [], 0

        for block in page.blocks:
            blk_tokens = _estimate_tokens(block.text)
            blk_bbox = {
                "page": block.page_number,
                "x0": block.x0,
                "y0": block.y0,
                "x1": block.x1,
                "y1": block.y1,
                "page_width": block.page_width,
                "page_height": block.page_height,
            }

            if blk_tokens > max_tokens:
                flush_buffer()
                sentences = _split_sentences(block.text)
                sent_buf: list[str] = []
                sent_tokens = 0
                for sent in sentences:
                    st = _estimate_tokens(sent)
                    if sent_buf and sent_tokens + st > max_tokens:
                        joined_sent = " ".join(sent_buf).strip()
                        chunks.append(
                            ChunkDraft(
                                chunk_index=chunk_idx,
                                page_number=page.page_number,
                                section_temp_id=section.temp_id,
                                section_title=section.title,
                                section_path=section.section_path,
                                text=joined_sent,
                                token_count=_estimate_tokens(joined_sent),
                                bbox_json=[blk_bbox],
                                ocr_used=block.ocr_used,
                                ocr_confidence=block.ocr_confidence,
                                metadata_json={
                                    "section_title": section.title,
                                    "section_path": section.section_path,
                                    "ocr_low_quality": page.ocr_low_quality,
                                },
                            )
                        )
                        chunk_idx += 1
                        sent_buf = [sent_buf[-1]] if _estimate_tokens(sent_buf[-1]) <= overlap_tokens else []
                        sent_tokens = _estimate_tokens(sent_buf[0]) if sent_buf else 0
                    sent_buf.append(sent)
                    sent_tokens += st
                if sent_buf:
                    joined_sent = " ".join(sent_buf).strip()
                    chunks.append(
                        ChunkDraft(
                            chunk_index=chunk_idx,
                            page_number=page.page_number,
                            section_temp_id=section.temp_id,
                            section_title=section.title,
                            section_path=section.section_path,
                            text=joined_sent,
                            token_count=_estimate_tokens(joined_sent),
                            bbox_json=[blk_bbox],
                            ocr_used=block.ocr_used,
                            ocr_confidence=block.ocr_confidence,
                            metadata_json={
                                "section_title": section.title,
                                "section_path": section.section_path,
                                "ocr_low_quality": page.ocr_low_quality,
                            },
                        )
                    )
                    chunk_idx += 1
                continue

            if buf_texts and buf_tokens + blk_tokens > max_tokens:
                flush_buffer()

            buf_texts.append(block.text)
            buf_bboxes.append(blk_bbox)
            buf_tokens += blk_tokens
            if block.ocr_used:
                buf_ocr_used = True
                buf_ocr_conf = block.ocr_confidence

        flush_buffer()

    return chunks
