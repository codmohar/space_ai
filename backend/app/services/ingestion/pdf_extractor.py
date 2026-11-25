"""PDF text, ToC, bounding-box, and Tesseract OCR extraction via PyMuPDF."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf as fitz  # PyMuPDF

logger = logging.getLogger(__name__)

MIN_NATIVE_CHARS_PER_PAGE = 40
MIN_OCR_MEAN_CONFIDENCE = 55.0
MIN_OCR_ALNUM_RATIO = 0.55
OCR_RENDER_DPI = 250


@dataclass
class ExtractedBlock:
    page_number: int
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    page_width: float
    page_height: float
    max_font_size: float = 10.0
    is_bold: bool = False
    ocr_used: bool = False
    ocr_confidence: float | None = None


@dataclass
class ExtractedSection:
    temp_id: int
    parent_temp_id: int | None
    title: str
    level: int
    section_path: str
    page_start: int
    page_end: int
    order_index: int
    is_leaf: bool = True


@dataclass
class ExtractedPage:
    page_number: int
    width: float
    height: float
    ocr_used: bool
    ocr_confidence: float | None
    ocr_low_quality: bool
    blocks: list[ExtractedBlock] = field(default_factory=list)


@dataclass
class ExtractedDocument:
    page_count: int
    pdf_metadata: dict[str, Any]
    sections: list[ExtractedSection]
    pages: list[ExtractedPage]
    ocr_pages: int
    low_quality_ocr_pages: list[int]


def evaluate_ocr_quality(words: list[str], confidences: list[float]) -> tuple[float, float, bool]:
    """Return (mean_confidence, alnum_ratio, is_low_quality)."""
    valid_confs = [c for c in confidences if c >= 0]
    mean_conf = sum(valid_confs) / len(valid_confs) if valid_confs else 0.0
    joined = "".join(words)
    if not joined:
        return mean_conf, 0.0, True
    alnum = sum(1 for ch in joined if ch.isalnum())
    alnum_ratio = alnum / len(joined)
    low_quality = mean_conf < MIN_OCR_MEAN_CONFIDENCE or alnum_ratio < MIN_OCR_ALNUM_RATIO
    return round(mean_conf, 2), round(alnum_ratio, 3), low_quality


def _needs_ocr(blocks: list[ExtractedBlock]) -> bool:
    raw = "".join(b.text for b in blocks)
    stripped = re.sub(r"\s+", "", raw)
    if len(stripped) < MIN_NATIVE_CHARS_PER_PAGE:
        return True
    cid_matches = len(re.findall(r"\(cid:\d+\)", raw))
    if cid_matches > 3:
        return True
    printable_alnum = sum(1 for ch in stripped if ch.isalnum())
    if stripped and (printable_alnum / len(stripped)) < 0.35:
        return True
    return False


def _extract_native_blocks(page: fitz.Page, page_number: int) -> list[ExtractedBlock]:
    page_rect = page.rect
    width = float(page_rect.width)
    height = float(page_rect.height)
    page_dict = page.get_text("dict")
    blocks: list[ExtractedBlock] = []

    for blk in page_dict.get("blocks", []):
        if blk.get("type") != 0:
            continue
        lines_text: list[str] = []
        max_font = 0.0
        bold = False
        for line in blk.get("lines", []):
            span_texts: list[str] = []
            for span in line.get("spans", []):
                stext = span.get("text", "")
                if stext:
                    span_texts.append(stext)
                    fsize = float(span.get("size", 10.0))
                    if fsize > max_font:
                        max_font = fsize
                    if int(span.get("flags", 0)) & 16:
                        bold = True
            line_joined = "".join(span_texts).strip()
            if line_joined:
                lines_text.append(line_joined)

        full_text = "\n".join(lines_text).strip()
        if not full_text:
            continue
        x0, y0, x1, y1 = [round(float(v), 2) for v in blk.get("bbox", (0, 0, width, height))]
        blocks.append(
            ExtractedBlock(
                page_number=page_number,
                text=full_text,
                x0=x0,
                y0=y0,
                x1=x1,
                y1=y1,
                page_width=width,
                page_height=height,
                max_font_size=max_font or 10.0,
                is_bold=bold,
                ocr_used=False,
            )
        )
    return blocks


def _extract_ocr_blocks(page: fitz.Page, page_number: int) -> tuple[list[ExtractedBlock], float, bool]:
    import io
    from PIL import Image
    import pytesseract

    pix = page.get_pixmap(dpi=OCR_RENDER_DPI)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    scale = 72.0 / OCR_RENDER_DPI
    width = float(page.rect.width)
    height = float(page.rect.height)

    words: list[str] = []
    confs: list[float] = []
    grouped_lines: dict[tuple[int, int, int], list[tuple[str, float, float, float, float]]] = {}

    n = len(data.get("text", []))
    for i in range(n):
        word = (data["text"][i] or "").strip()
        try:
            conf = float(data["conf"][i])
        except (ValueError, TypeError):
            conf = -1.0
        if not word:
            continue
        words.append(word)
        confs.append(conf)
        key = (
            int(data["block_num"][i]),
            int(data["par_num"][i]),
            int(data["line_num"][i]),
        )
        left = float(data["left"][i]) * scale
        top = float(data["top"][i]) * scale
        right = (float(data["left"][i]) + float(data["width"][i])) * scale
        bottom = (float(data["top"][i]) + float(data["height"][i])) * scale
        grouped_lines.setdefault(key, []).append((word, left, top, right, bottom))

    mean_conf, _alnum_ratio, low_quality = evaluate_ocr_quality(words, confs)

    blocks_by_num: dict[int, list[tuple[str, float, float, float, float]]] = {}
    for (blk_num, _par, _line), line_words in sorted(grouped_lines.items()):
        line_text = " ".join(w[0] for w in line_words)
        lx0 = min(w[1] for w in line_words)
        ly0 = min(w[2] for w in line_words)
        lx1 = max(w[3] for w in line_words)
        ly1 = max(w[4] for w in line_words)
        blocks_by_num.setdefault(blk_num, []).append((line_text, lx0, ly0, lx1, ly1))

    blocks: list[ExtractedBlock] = []
    for _blk_num, lines in sorted(blocks_by_num.items()):
        text = "\n".join(l[0] for l in lines).strip()
        if not text:
            continue
        bx0 = round(min(l[1] for l in lines), 2)
        by0 = round(min(l[2] for l in lines), 2)
        bx1 = round(max(l[3] for l in lines), 2)
        by1 = round(max(l[4] for l in lines), 2)
        blocks.append(
            ExtractedBlock(
                page_number=page_number,
                text=text,
                x0=bx0,
                y0=by0,
                x1=bx1,
                y1=by1,
                page_width=width,
                page_height=height,
                ocr_used=True,
                ocr_confidence=mean_conf,
            )
        )

    return blocks, mean_conf, low_quality


def _build_sections_from_toc(raw_toc: list[list[Any]], page_count: int) -> list[ExtractedSection]:
    sections: list[ExtractedSection] = []
    parent_stack: list[tuple[int, int]] = []  # (level, temp_id)
    counters: list[int] = []

    for idx, item in enumerate(raw_toc):
        level = max(1, int(item[0]))
        title = str(item[1]).strip() or f"Section {idx + 1}"
        page_start = max(1, min(page_count, int(item[2]) if len(item) > 2 else 1))

        while parent_stack and parent_stack[-1][0] >= level:
            parent_stack.pop()
        parent_id = parent_stack[-1][1] if parent_stack else None

        while len(counters) < level:
            counters.append(0)
        counters = counters[:level]
        counters[-1] += 1
        section_path = ".".join(str(c) for c in counters)

        sec = ExtractedSection(
            temp_id=idx + 1,
            parent_temp_id=parent_id,
            title=title[:500],
            level=level,
            section_path=section_path,
            page_start=page_start,
            page_end=page_count,
            order_index=idx,
        )
        sections.append(sec)
        parent_stack.append((level, sec.temp_id))

    # Compute page_end and is_leaf
    parent_ids = {s.parent_temp_id for s in sections if s.parent_temp_id is not None}
    for i, sec in enumerate(sections):
        sec.is_leaf = sec.temp_id not in parent_ids
        # End at page before next sibling/higher-level section starts (min page_start)
        for nxt in sections[i + 1 :]:
            if nxt.level <= sec.level:
                sec.page_end = max(sec.page_start, nxt.page_start)
                break

    return sections


def _build_sections_from_heuristics(pages: list[ExtractedPage]) -> list[ExtractedSection]:
    font_sizes = [
        b.max_font_size
        for p in pages
        for b in p.blocks
        if not b.ocr_used and len(b.text) < 160
    ]
    median_size = sorted(font_sizes)[len(font_sizes) // 2] if font_sizes else 10.5
    heading_threshold = median_size * 1.18

    sections: list[ExtractedSection] = []
    idx = 0
    for page in pages:
        for blk in page.blocks:
            first_line = blk.text.splitlines()[0].strip()
            is_numbered = bool(re.match(r"^(?:\d+(?:\.\d+)*|[IVX]+)\s+[A-Z]", first_line))
            looks_like_heading = (
                len(first_line) <= 120
                and len(blk.text) <= 160
                and (blk.max_font_size >= heading_threshold or (blk.is_bold and is_numbered))
            )
            if looks_like_heading:
                sections.append(
                    ExtractedSection(
                        temp_id=idx + 1,
                        parent_temp_id=None,
                        title=first_line,
                        level=1,
                        section_path=str(idx + 1),
                        page_start=page.page_number,
                        page_end=len(pages),
                        order_index=idx,
                        is_leaf=True,
                    )
                )
                idx += 1

    if not sections:
        sections.append(
            ExtractedSection(
                temp_id=1,
                parent_temp_id=None,
                title="Document Body",
                level=1,
                section_path="1",
                page_start=1,
                page_end=max(1, len(pages)),
                order_index=0,
                is_leaf=True,
            )
        )
    else:
        for i, sec in enumerate(sections[:-1]):
            sec.page_end = max(sec.page_start, sections[i + 1].page_start)

    return sections


def extract_pdf(pdf_path: Path) -> ExtractedDocument:
    """Extract ToC/sections, page text blocks, bounding boxes, and OCR fallback."""
    doc = fitz.open(str(pdf_path))
    try:
        page_count = len(doc)
        pdf_metadata = dict(doc.metadata or {})
        pages: list[ExtractedPage] = []
        ocr_pages = 0
        low_quality_ocr_pages: list[int] = []

        for page_idx in range(page_count):
            page_number = page_idx + 1
            page = doc[page_idx]
            width = float(page.rect.width)
            height = float(page.rect.height)

            blocks = _extract_native_blocks(page, page_number)
            ocr_used = False
            ocr_conf: float | None = None
            ocr_low_q = False

            if _needs_ocr(blocks):
                try:
                    ocr_blocks, ocr_conf, ocr_low_q = _extract_ocr_blocks(page, page_number)
                    if ocr_blocks:
                        blocks = ocr_blocks
                        ocr_used = True
                        ocr_pages += 1
                        if ocr_low_q:
                            low_quality_ocr_pages.append(page_number)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("OCR fallback failed on page %d of %s: %s", page_number, pdf_path.name, exc)

            pages.append(
                ExtractedPage(
                    page_number=page_number,
                    width=width,
                    height=height,
                    ocr_used=ocr_used,
                    ocr_confidence=ocr_conf,
                    ocr_low_quality=ocr_low_q,
                    blocks=blocks,
                )
            )

        raw_toc = doc.get_toc(simple=True)
        if raw_toc:
            sections = _build_sections_from_toc(raw_toc, page_count)
        else:
            sections = _build_sections_from_heuristics(pages)

        return ExtractedDocument(
            page_count=page_count,
            pdf_metadata=pdf_metadata,
            sections=sections,
            pages=pages,
            ocr_pages=ocr_pages,
            low_quality_ocr_pages=low_quality_ocr_pages,
        )
    finally:
        doc.close()
