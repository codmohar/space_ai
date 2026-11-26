"""Multi-format document parsers for MISSIONWISE AI.

Supports format-specific extraction into unified ExtractedDocument:
- PDF / Scanned PDF (PyMuPDF + Tesseract OCR)
- Word Documents (.docx)
- PowerPoint Presentations (.pptx)
- Plain Text (.txt)
- Markdown (.md)
- HTML Documents (.html, .htm)
- Spreadsheets & Data (.csv, .xlsx)
- XML Data (.xml)
- Scanned Images (.png, .jpg, .jpeg, .tiff, .tif via Tesseract OCR)
"""

from __future__ import annotations

import csv
import io
import logging
import re
import xml.etree.ElementTree as ET
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Optional

from PIL import Image

from app.core.errors import ApiError
from app.services.ingestion.pdf_extractor import (
    ExtractedBlock,
    ExtractedDocument,
    ExtractedPage,
    ExtractedSection,
    evaluate_ocr_quality,
    extract_pdf,
)

logger = logging.getLogger(__name__)

PAGE_DEFAULT_WIDTH = 612.0  # Standard letter 8.5in * 72
PAGE_DEFAULT_HEIGHT = 792.0  # Standard letter 11in * 72
TEXT_LINES_PER_PAGE = 45


def _clean_text(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).strip()


# ---------------------------------------------------------------------------
# 1. Plain Text (.txt)
# ---------------------------------------------------------------------------
def parse_text(raw_bytes: bytes, filename: str) -> ExtractedDocument:
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            content = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        content = raw_bytes.decode("utf-8", errors="replace")

    raw_lines = content.splitlines()
    pages: list[ExtractedPage] = []
    sections: list[ExtractedSection] = []

    current_page_blocks: list[ExtractedBlock] = []
    current_page_lines: list[str] = []
    page_number = 1
    sec_id = 1
    y_cursor = 40.0
    line_height = 14.0

    # Fallback root section
    root_title = Path(filename).stem.replace("_", " ").title()
    sections.append(
        ExtractedSection(
            temp_id=sec_id,
            parent_temp_id=None,
            title=root_title,
            level=1,
            section_path="1.0",
            page_start=1,
            page_end=1,
            order_index=0,
            is_leaf=True,
            extraction_method="text_heading",
        )
    )

    for line in raw_lines:
        stripped = line.strip()
        # Form-feed or length-based page split
        if "\x0c" in line or len(current_page_lines) >= TEXT_LINES_PER_PAGE:
            pages.append(
                ExtractedPage(
                    page_number=page_number,
                    width=PAGE_DEFAULT_WIDTH,
                    height=PAGE_DEFAULT_HEIGHT,
                    ocr_used=False,
                    ocr_confidence=None,
                    ocr_low_quality=False,
                    blocks=current_page_blocks,
                )
            )
            page_number += 1
            current_page_blocks = []
            current_page_lines = []
            y_cursor = 40.0

        if not stripped:
            continue

        current_page_lines.append(stripped)
        # Check if line looks like a heading (e.g. "1.0 INTRODUCTION", "SECTION 2", or all caps short)
        is_heading = (
            bool(re.match(r"^(?:[0-9]+(?:\.[0-9]+)*\s+[A-Z]|SECTION\s+[0-9A-Z]|CHAPTER\s+[0-9A-Z])", stripped, re.I))
            or (stripped.isupper() and len(stripped.split()) <= 8 and len(stripped) >= 4)
        )

        if is_heading:
            sec_id += 1
            match_num = re.match(r"^([0-9]+(?:\.[0-9]+)*)", stripped)
            sec_path = match_num.group(1) if match_num else f"1.{sec_id}"
            level = min(3, len(sec_path.split(".")))
            sections.append(
                ExtractedSection(
                    temp_id=sec_id,
                    parent_temp_id=1,
                    title=stripped,
                    level=level,
                    section_path=sec_path,
                    page_start=page_number,
                    page_end=page_number,
                    order_index=len(sections),
                    is_leaf=True,
                    extraction_method="text_heading",
                )
            )

        current_page_blocks.append(
            ExtractedBlock(
                page_number=page_number,
                text=stripped,
                x0=54.0,
                y0=y_cursor,
                x1=PAGE_DEFAULT_WIDTH - 54.0,
                y1=y_cursor + line_height,
                page_width=PAGE_DEFAULT_WIDTH,
                page_height=PAGE_DEFAULT_HEIGHT,
                max_font_size=12.0 if is_heading else 10.0,
                is_bold=is_heading,
            )
        )
        y_cursor += line_height

    if current_page_blocks or not pages:
        pages.append(
            ExtractedPage(
                page_number=page_number,
                width=PAGE_DEFAULT_WIDTH,
                height=PAGE_DEFAULT_HEIGHT,
                ocr_used=False,
                ocr_confidence=None,
                ocr_low_quality=False,
                blocks=current_page_blocks,
            )
        )

    for sec in sections:
        sec.page_end = page_number

    return ExtractedDocument(
        page_count=len(pages),
        pdf_metadata={"format": "txt", "filename": filename},
        sections=sections,
        pages=pages,
        ocr_pages=0,
        low_quality_ocr_pages=[],
        toc_extraction_method="text_heading",
    )


# ---------------------------------------------------------------------------
# 2. Markdown (.md)
# ---------------------------------------------------------------------------
def parse_markdown(raw_bytes: bytes, filename: str) -> ExtractedDocument:
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            content = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        content = raw_bytes.decode("utf-8", errors="replace")

    raw_lines = content.splitlines()
    pages: list[ExtractedPage] = []
    sections: list[ExtractedSection] = []

    current_blocks: list[ExtractedBlock] = []
    page_number = 1
    sec_id = 0
    y_cursor = 40.0
    line_count = 0

    root_title = Path(filename).stem.replace("_", " ").title()
    sections.append(
        ExtractedSection(
            temp_id=1,
            parent_temp_id=None,
            title=root_title,
            level=1,
            section_path="1.0",
            page_start=1,
            page_end=1,
            order_index=0,
            is_leaf=True,
            extraction_method="markdown_heading",
        )
    )
    sec_id = 1

    for line in raw_lines:
        stripped = line.strip()
        if stripped == "---" or line_count >= TEXT_LINES_PER_PAGE:
            pages.append(
                ExtractedPage(
                    page_number=page_number,
                    width=PAGE_DEFAULT_WIDTH,
                    height=PAGE_DEFAULT_HEIGHT,
                    ocr_used=False,
                    ocr_confidence=None,
                    ocr_low_quality=False,
                    blocks=current_blocks,
                )
            )
            page_number += 1
            current_blocks = []
            y_cursor = 40.0
            line_count = 0
            if stripped == "---":
                continue

        if not stripped:
            continue

        line_count += 1
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            hashes, heading_text = heading_match.groups()
            level = min(4, len(hashes))
            sec_id += 1
            sec_path = f"{level}.{sec_id}"
            sections.append(
                ExtractedSection(
                    temp_id=sec_id,
                    parent_temp_id=1 if level > 1 else None,
                    title=heading_text.strip(),
                    level=level,
                    section_path=sec_path,
                    page_start=page_number,
                    page_end=page_number,
                    order_index=len(sections),
                    is_leaf=True,
                    extraction_method="markdown_heading",
                )
            )
            current_blocks.append(
                ExtractedBlock(
                    page_number=page_number,
                    text=heading_text.strip(),
                    x0=54.0,
                    y0=y_cursor,
                    x1=PAGE_DEFAULT_WIDTH - 54.0,
                    y1=y_cursor + 18.0,
                    page_width=PAGE_DEFAULT_WIDTH,
                    page_height=PAGE_DEFAULT_HEIGHT,
                    max_font_size=16.0 - (level * 1.5),
                    is_bold=True,
                )
            )
            y_cursor += 20.0
        else:
            current_blocks.append(
                ExtractedBlock(
                    page_number=page_number,
                    text=stripped,
                    x0=54.0,
                    y0=y_cursor,
                    x1=PAGE_DEFAULT_WIDTH - 54.0,
                    y1=y_cursor + 14.0,
                    page_width=PAGE_DEFAULT_WIDTH,
                    page_height=PAGE_DEFAULT_HEIGHT,
                    max_font_size=10.0,
                    is_bold=False,
                )
            )
            y_cursor += 15.0

    if current_blocks or not pages:
        pages.append(
            ExtractedPage(
                page_number=page_number,
                width=PAGE_DEFAULT_WIDTH,
                height=PAGE_DEFAULT_HEIGHT,
                ocr_used=False,
                ocr_confidence=None,
                ocr_low_quality=False,
                blocks=current_blocks,
            )
        )

    for sec in sections:
        sec.page_end = page_number

    return ExtractedDocument(
        page_count=len(pages),
        pdf_metadata={"format": "md", "filename": filename},
        sections=sections,
        pages=pages,
        ocr_pages=0,
        low_quality_ocr_pages=[],
        toc_extraction_method="markdown_heading",
    )


# ---------------------------------------------------------------------------
# 3. HTML (.html, .htm)
# ---------------------------------------------------------------------------
def parse_html(raw_bytes: bytes, filename: str) -> ExtractedDocument:
    from bs4 import BeautifulSoup

    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            html_text = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        html_text = raw_bytes.decode("utf-8", errors="replace")

    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    title_tag = soup.find("title")
    doc_title = title_tag.get_text().strip() if title_tag else Path(filename).stem.replace("_", " ").title()

    sections: list[ExtractedSection] = [
        ExtractedSection(
            temp_id=1,
            parent_temp_id=None,
            title=doc_title,
            level=1,
            section_path="1.0",
            page_start=1,
            page_end=1,
            order_index=0,
            is_leaf=True,
            extraction_method="html_heading",
        )
    ]
    sec_id = 1
    page_number = 1
    blocks: list[ExtractedBlock] = []
    y_cursor = 40.0

    # Process headings, paragraphs, and tables
    for elem in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "table", "li"]):
        tag_name = elem.name.lower()
        if tag_name.startswith("h"):
            h_level = int(tag_name[1])
            h_text = elem.get_text().strip()
            if not h_text:
                continue
            sec_id += 1
            sections.append(
                ExtractedSection(
                    temp_id=sec_id,
                    parent_temp_id=1 if h_level > 1 else None,
                    title=h_text,
                    level=min(4, h_level),
                    section_path=f"{h_level}.{sec_id}",
                    page_start=page_number,
                    page_end=page_number,
                    order_index=len(sections),
                    is_leaf=True,
                    extraction_method="html_heading",
                )
            )
            blocks.append(
                ExtractedBlock(
                    page_number=page_number,
                    text=h_text,
                    x0=54.0,
                    y0=y_cursor,
                    x1=PAGE_DEFAULT_WIDTH - 54.0,
                    y1=y_cursor + 18.0,
                    page_width=PAGE_DEFAULT_WIDTH,
                    page_height=PAGE_DEFAULT_HEIGHT,
                    max_font_size=15.0 - h_level,
                    is_bold=True,
                )
            )
            y_cursor += 20.0
        elif tag_name == "table":
            # Convert table to markdown table format
            table_lines: list[str] = []
            rows = elem.find_all("tr")
            for r_idx, row in enumerate(rows):
                cells = [c.get_text().strip().replace("\n", " ") for c in row.find_all(["th", "td"])]
                if cells:
                    table_lines.append("| " + " | ".join(cells) + " |")
                    if r_idx == 0:
                        table_lines.append("| " + " | ".join(["---"] * len(cells)) + " |")
            if table_lines:
                tbl_text = "\n".join(table_lines)
                blocks.append(
                    ExtractedBlock(
                        page_number=page_number,
                        text=tbl_text,
                        x0=54.0,
                        y0=y_cursor,
                        x1=PAGE_DEFAULT_WIDTH - 54.0,
                        y1=y_cursor + (len(table_lines) * 14.0),
                        page_width=PAGE_DEFAULT_WIDTH,
                        page_height=PAGE_DEFAULT_HEIGHT,
                        max_font_size=9.5,
                        is_bold=False,
                    )
                )
                y_cursor += len(table_lines) * 15.0
        else:
            p_text = elem.get_text().strip()
            if p_text:
                blocks.append(
                    ExtractedBlock(
                        page_number=page_number,
                        text=p_text,
                        x0=54.0,
                        y0=y_cursor,
                        x1=PAGE_DEFAULT_WIDTH - 54.0,
                        y1=y_cursor + 14.0,
                        page_width=PAGE_DEFAULT_WIDTH,
                        page_height=PAGE_DEFAULT_HEIGHT,
                        max_font_size=10.0,
                        is_bold=False,
                    )
                )
                y_cursor += 16.0

        if y_cursor >= PAGE_DEFAULT_HEIGHT - 60.0:
            page_number += 1
            y_cursor = 40.0

    # Paginate blocks
    pages = [
        ExtractedPage(
            page_number=1,
            width=PAGE_DEFAULT_WIDTH,
            height=PAGE_DEFAULT_HEIGHT,
            ocr_used=False,
            ocr_confidence=None,
            ocr_low_quality=False,
            blocks=blocks,
        )
    ]

    for sec in sections:
        sec.page_end = 1

    return ExtractedDocument(
        page_count=1,
        pdf_metadata={"format": "html", "filename": filename, "title": doc_title},
        sections=sections,
        pages=pages,
        ocr_pages=0,
        low_quality_ocr_pages=[],
        toc_extraction_method="html_heading",
    )


# ---------------------------------------------------------------------------
# 4. Microsoft Word (.docx)
# ---------------------------------------------------------------------------
def parse_docx(raw_bytes: bytes, filename: str) -> ExtractedDocument:
    import docx

    doc = docx.Document(BytesIO(raw_bytes))
    doc_title = Path(filename).stem.replace("_", " ").title()

    sections: list[ExtractedSection] = [
        ExtractedSection(
            temp_id=1,
            parent_temp_id=None,
            title=doc_title,
            level=1,
            section_path="1.0",
            page_start=1,
            page_end=1,
            order_index=0,
            is_leaf=True,
            extraction_method="docx_style",
        )
    ]
    sec_id = 1
    page_number = 1
    blocks: list[ExtractedBlock] = []
    y_cursor = 40.0

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        style_name = para.style.name.lower() if para.style else ""
        is_heading = "heading" in style_name or "title" in style_name
        h_level = 1
        if "heading 1" in style_name:
            h_level = 1
        elif "heading 2" in style_name:
            h_level = 2
        elif "heading 3" in style_name:
            h_level = 3
        elif "heading 4" in style_name:
            h_level = 4

        if is_heading:
            sec_id += 1
            sections.append(
                ExtractedSection(
                    temp_id=sec_id,
                    parent_temp_id=1 if h_level > 1 else None,
                    title=text,
                    level=min(4, h_level),
                    section_path=f"{h_level}.{sec_id}",
                    page_start=page_number,
                    page_end=page_number,
                    order_index=len(sections),
                    is_leaf=True,
                    extraction_method="docx_style",
                )
            )

        blocks.append(
            ExtractedBlock(
                page_number=page_number,
                text=text,
                x0=54.0,
                y0=y_cursor,
                x1=PAGE_DEFAULT_WIDTH - 54.0,
                y1=y_cursor + (18.0 if is_heading else 14.0),
                page_width=PAGE_DEFAULT_WIDTH,
                page_height=PAGE_DEFAULT_HEIGHT,
                max_font_size=14.0 if is_heading else 10.0,
                is_bold=is_heading,
            )
        )
        y_cursor += 18.0 if is_heading else 15.0
        if y_cursor >= PAGE_DEFAULT_HEIGHT - 60.0:
            page_number += 1
            y_cursor = 40.0

    # Extract tables
    for table in doc.tables:
        table_lines: list[str] = []
        for r_idx, row in enumerate(table.rows):
            cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            if cells:
                table_lines.append("| " + " | ".join(cells) + " |")
                if r_idx == 0:
                    table_lines.append("| " + " | ".join(["---"] * len(cells)) + " |")
        if table_lines:
            blocks.append(
                ExtractedBlock(
                    page_number=page_number,
                    text="\n".join(table_lines),
                    x0=54.0,
                    y0=y_cursor,
                    x1=PAGE_DEFAULT_WIDTH - 54.0,
                    y1=y_cursor + (len(table_lines) * 14.0),
                    page_width=PAGE_DEFAULT_WIDTH,
                    page_height=PAGE_DEFAULT_HEIGHT,
                    max_font_size=9.5,
                    is_bold=False,
                )
            )
            y_cursor += len(table_lines) * 15.0

    pages = [
        ExtractedPage(
            page_number=1,
            width=PAGE_DEFAULT_WIDTH,
            height=PAGE_DEFAULT_HEIGHT,
            ocr_used=False,
            ocr_confidence=None,
            ocr_low_quality=False,
            blocks=blocks,
        )
    ]

    for sec in sections:
        sec.page_end = 1

    return ExtractedDocument(
        page_count=1,
        pdf_metadata={"format": "docx", "filename": filename},
        sections=sections,
        pages=pages,
        ocr_pages=0,
        low_quality_ocr_pages=[],
        toc_extraction_method="docx_style",
    )


# ---------------------------------------------------------------------------
# 5. PowerPoint (.pptx)
# ---------------------------------------------------------------------------
def parse_pptx(raw_bytes: bytes, filename: str) -> ExtractedDocument:
    import pptx

    prs = pptx.Presentation(BytesIO(raw_bytes))
    doc_title = Path(filename).stem.replace("_", " ").title()

    sections: list[ExtractedSection] = []
    pages: list[ExtractedPage] = []
    sec_id = 0

    for idx, slide in enumerate(prs.slides, start=1):
        slide_title = ""
        slide_blocks: list[ExtractedBlock] = []
        y_cursor = 40.0

        for shape in slide.shapes:
            if shape.has_text_frame:
                text = shape.text_frame.text.strip()
                if not text:
                    continue
                if not slide_title:
                    slide_title = text.splitlines()[0][:120]

                slide_blocks.append(
                    ExtractedBlock(
                        page_number=idx,
                        text=text,
                        x0=54.0,
                        y0=y_cursor,
                        x1=PAGE_DEFAULT_WIDTH - 54.0,
                        y1=y_cursor + 20.0,
                        page_width=PAGE_DEFAULT_WIDTH,
                        page_height=PAGE_DEFAULT_HEIGHT,
                        max_font_size=12.0,
                        is_bold=False,
                    )
                )
                y_cursor += 24.0

        sec_id += 1
        sec_title = slide_title or f"Slide {idx}"
        sections.append(
            ExtractedSection(
                temp_id=sec_id,
                parent_temp_id=None,
                title=f"Slide {idx}: {sec_title}",
                level=1,
                section_path=f"1.{sec_id}",
                page_start=idx,
                page_end=idx,
                order_index=len(sections),
                is_leaf=True,
                extraction_method="pptx_slide",
            )
        )
        pages.append(
            ExtractedPage(
                page_number=idx,
                width=PAGE_DEFAULT_WIDTH,
                height=PAGE_DEFAULT_HEIGHT,
                ocr_used=False,
                ocr_confidence=None,
                ocr_low_quality=False,
                blocks=slide_blocks,
            )
        )

    if not pages:
        pages.append(
            ExtractedPage(
                page_number=1,
                width=PAGE_DEFAULT_WIDTH,
                height=PAGE_DEFAULT_HEIGHT,
                ocr_used=False,
                ocr_confidence=None,
                ocr_low_quality=False,
                blocks=[],
            )
        )

    return ExtractedDocument(
        page_count=len(pages),
        pdf_metadata={"format": "pptx", "filename": filename, "title": doc_title},
        sections=sections,
        pages=pages,
        ocr_pages=0,
        low_quality_ocr_pages=[],
        toc_extraction_method="pptx_slide",
    )


# ---------------------------------------------------------------------------
# 6. CSV (.csv)
# ---------------------------------------------------------------------------
def parse_csv(raw_bytes: bytes, filename: str) -> ExtractedDocument:
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            content = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        content = raw_bytes.decode("utf-8", errors="replace")

    reader = csv.reader(StringIO(content))
    rows = list(reader)
    if not rows:
        raise ApiError("EMPTY_FILE", "CSV file contains no data.", status_code=400)

    header = rows[0]
    data_rows = rows[1:]
    doc_title = Path(filename).stem.replace("_", " ").title()

    sections: list[ExtractedSection] = [
        ExtractedSection(
            temp_id=1,
            parent_temp_id=None,
            title=doc_title,
            level=1,
            section_path="1.0",
            page_start=1,
            page_end=1,
            order_index=0,
            is_leaf=True,
            extraction_method="csv_table",
        )
    ]

    # Group into pages of 40 rows each
    pages: list[ExtractedPage] = []
    chunk_size = 40
    page_number = 1

    for start_idx in range(0, max(1, len(data_rows)), chunk_size):
        chunk_rows = data_rows[start_idx : start_idx + chunk_size]
        table_lines: list[str] = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(["---"] * len(header)) + " |",
        ]
        for row in chunk_rows:
            # Pad or truncate row to header length
            padded = row[: len(header)] + [""] * max(0, len(header) - len(row))
            table_lines.append("| " + " | ".join(c.replace("\n", " ").strip() for c in padded) + " |")

        tbl_text = "\n".join(table_lines)
        page_blocks = [
            ExtractedBlock(
                page_number=page_number,
                text=tbl_text,
                x0=54.0,
                y0=40.0,
                x1=PAGE_DEFAULT_WIDTH - 54.0,
                y1=PAGE_DEFAULT_HEIGHT - 40.0,
                page_width=PAGE_DEFAULT_WIDTH,
                page_height=PAGE_DEFAULT_HEIGHT,
                max_font_size=9.5,
                is_bold=False,
            )
        ]
        pages.append(
            ExtractedPage(
                page_number=page_number,
                width=PAGE_DEFAULT_WIDTH,
                height=PAGE_DEFAULT_HEIGHT,
                ocr_used=False,
                ocr_confidence=None,
                ocr_low_quality=False,
                blocks=page_blocks,
            )
        )
        page_number += 1

    sections[0].page_end = len(pages)

    return ExtractedDocument(
        page_count=len(pages),
        pdf_metadata={"format": "csv", "filename": filename, "row_count": len(data_rows)},
        sections=sections,
        pages=pages,
        ocr_pages=0,
        low_quality_ocr_pages=[],
        toc_extraction_method="csv_table",
    )


# ---------------------------------------------------------------------------
# 7. Excel (.xlsx)
# ---------------------------------------------------------------------------
def parse_xlsx(raw_bytes: bytes, filename: str) -> ExtractedDocument:
    import openpyxl

    wb = openpyxl.load_workbook(BytesIO(raw_bytes), data_only=True, read_only=True)
    doc_title = Path(filename).stem.replace("_", " ").title()

    sections: list[ExtractedSection] = []
    pages: list[ExtractedPage] = []
    page_number = 1
    sec_id = 0

    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            continue

        sec_id += 1
        sheet_start_page = page_number
        header = [str(c or "").strip() for c in rows[0]]
        data_rows = rows[1:]

        chunk_size = 40
        for start_idx in range(0, max(1, len(data_rows)), chunk_size):
            chunk_rows = data_rows[start_idx : start_idx + chunk_size]
            table_lines: list[str] = [
                "| " + " | ".join(header) + " |",
                "| " + " | ".join(["---"] * len(header)) + " |",
            ]
            for row in chunk_rows:
                str_cells = [str(c or "").replace("\n", " ").strip() for c in row]
                padded = str_cells[: len(header)] + [""] * max(0, len(header) - len(str_cells))
                table_lines.append("| " + " | ".join(padded) + " |")

            pages.append(
                ExtractedPage(
                    page_number=page_number,
                    width=PAGE_DEFAULT_WIDTH,
                    height=PAGE_DEFAULT_HEIGHT,
                    ocr_used=False,
                    ocr_confidence=None,
                    ocr_low_quality=False,
                    blocks=[
                        ExtractedBlock(
                            page_number=page_number,
                            text="\n".join(table_lines),
                            x0=54.0,
                            y0=40.0,
                            x1=PAGE_DEFAULT_WIDTH - 54.0,
                            y1=PAGE_DEFAULT_HEIGHT - 40.0,
                            page_width=PAGE_DEFAULT_WIDTH,
                            page_height=PAGE_DEFAULT_HEIGHT,
                            max_font_size=9.5,
                            is_bold=False,
                        )
                    ],
                )
            )
            page_number += 1

        sections.append(
            ExtractedSection(
                temp_id=sec_id,
                parent_temp_id=None,
                title=f"Sheet: {sheet_name}",
                level=1,
                section_path=f"1.{sec_id}",
                page_start=sheet_start_page,
                page_end=max(sheet_start_page, page_number - 1),
                order_index=len(sections),
                is_leaf=True,
                extraction_method="xlsx_sheet",
            )
        )

    wb.close()
    if not pages:
        pages.append(
            ExtractedPage(
                page_number=1,
                width=PAGE_DEFAULT_WIDTH,
                height=PAGE_DEFAULT_HEIGHT,
                ocr_used=False,
                ocr_confidence=None,
                ocr_low_quality=False,
                blocks=[],
            )
        )

    return ExtractedDocument(
        page_count=len(pages),
        pdf_metadata={"format": "xlsx", "filename": filename},
        sections=sections,
        pages=pages,
        ocr_pages=0,
        low_quality_ocr_pages=[],
        toc_extraction_method="xlsx_sheet",
    )


# ---------------------------------------------------------------------------
# 8. XML (.xml)
# ---------------------------------------------------------------------------
def parse_xml(raw_bytes: bytes, filename: str) -> ExtractedDocument:
    # Reject XML entity injection attacks (billion laughs / XXE)
    if b"<!ENTITY" in raw_bytes or b"SYSTEM" in raw_bytes:
        raise ApiError(
            "XML_ENTITY_INJECTION_BLOCKED",
            "XML documents containing DTD entity declarations are prohibited.",
            status_code=400,
        )

    root = ET.fromstring(raw_bytes)
    doc_title = Path(filename).stem.replace("_", " ").title()

    sections: list[ExtractedSection] = [
        ExtractedSection(
            temp_id=1,
            parent_temp_id=None,
            title=doc_title,
            level=1,
            section_path="1.0",
            page_start=1,
            page_end=1,
            order_index=0,
            is_leaf=True,
            extraction_method="xml_element",
        )
    ]
    sec_id = 1
    blocks: list[ExtractedBlock] = []
    y_cursor = 40.0

    for child in root:
        tag_name = child.tag
        child_text = "".join(child.itertext()).strip()
        if not child_text:
            continue

        sec_id += 1
        sections.append(
            ExtractedSection(
                temp_id=sec_id,
                parent_temp_id=1,
                title=f"<{tag_name}>",
                level=2,
                section_path=f"2.{sec_id}",
                page_start=1,
                page_end=1,
                order_index=len(sections),
                is_leaf=True,
                extraction_method="xml_element",
            )
        )
        blocks.append(
            ExtractedBlock(
                page_number=1,
                text=f"<{tag_name}>: {child_text[:1000]}",
                x0=54.0,
                y0=y_cursor,
                x1=PAGE_DEFAULT_WIDTH - 54.0,
                y1=y_cursor + 20.0,
                page_width=PAGE_DEFAULT_WIDTH,
                page_height=PAGE_DEFAULT_HEIGHT,
                max_font_size=10.0,
                is_bold=False,
            )
        )
        y_cursor += 24.0

    pages = [
        ExtractedPage(
            page_number=1,
            width=PAGE_DEFAULT_WIDTH,
            height=PAGE_DEFAULT_HEIGHT,
            ocr_used=False,
            ocr_confidence=None,
            ocr_low_quality=False,
            blocks=blocks,
        )
    ]

    return ExtractedDocument(
        page_count=1,
        pdf_metadata={"format": "xml", "filename": filename, "root_tag": root.tag},
        sections=sections,
        pages=pages,
        ocr_pages=0,
        low_quality_ocr_pages=[],
        toc_extraction_method="xml_element",
    )


# ---------------------------------------------------------------------------
# 9. Scanned Image (.png, .jpg, .jpeg, .tiff, .tif) via OCR
# ---------------------------------------------------------------------------
def parse_image(raw_bytes: bytes, filename: str) -> ExtractedDocument:
    import pytesseract

    image = Image.open(BytesIO(raw_bytes))
    img_w, img_h = image.size
    doc_title = Path(filename).stem.replace("_", " ").title()

    # Run OCR with bounding boxes
    data = pytesseract.image_to_data(image, lang="eng", output_type=pytesseract.Output.DICT)

    words = data.get("text", [])
    confs = [float(c) for c in data.get("conf", [])]
    mean_conf, alnum_ratio, is_low_quality = evaluate_ocr_quality(words, confs)

    blocks: list[ExtractedBlock] = []
    line_words: list[str] = []
    cur_line = -1
    line_x0, line_y0, line_x1, line_y1 = 0.0, 0.0, 0.0, 0.0

    n_boxes = len(words)
    for i in range(n_boxes):
        w = words[i].strip()
        if not w:
            continue
        line_num = data["line_num"][i]
        x, y, w_box, h_box = data["left"][i], data["top"][i], data["width"][i], data["height"][i]

        if line_num != cur_line and line_words:
            blocks.append(
                ExtractedBlock(
                    page_number=1,
                    text=" ".join(line_words),
                    x0=round((line_x0 / img_w) * PAGE_DEFAULT_WIDTH, 1),
                    y0=round((line_y0 / img_h) * PAGE_DEFAULT_HEIGHT, 1),
                    x1=round((line_x1 / img_w) * PAGE_DEFAULT_WIDTH, 1),
                    y1=round((line_y1 / img_h) * PAGE_DEFAULT_HEIGHT, 1),
                    page_width=PAGE_DEFAULT_WIDTH,
                    page_height=PAGE_DEFAULT_HEIGHT,
                    ocr_used=True,
                    ocr_confidence=mean_conf,
                )
            )
            line_words = []

        cur_line = line_num
        line_words.append(w)
        line_x0 = min(line_x0, x) if line_words else x
        line_y0 = min(line_y0, y) if line_words else y
        line_x1 = max(line_x1, x + w_box)
        line_y1 = max(line_y1, y + h_box)

    if line_words:
        blocks.append(
            ExtractedBlock(
                page_number=1,
                text=" ".join(line_words),
                x0=round((line_x0 / img_w) * PAGE_DEFAULT_WIDTH, 1),
                y0=round((line_y0 / img_h) * PAGE_DEFAULT_HEIGHT, 1),
                x1=round((line_x1 / img_w) * PAGE_DEFAULT_WIDTH, 1),
                y1=round((line_y1 / img_h) * PAGE_DEFAULT_HEIGHT, 1),
                page_width=PAGE_DEFAULT_WIDTH,
                page_height=PAGE_DEFAULT_HEIGHT,
                ocr_used=True,
                ocr_confidence=mean_conf,
            )
        )

    sections = [
        ExtractedSection(
            temp_id=1,
            parent_temp_id=None,
            title=doc_title,
            level=1,
            section_path="1.0",
            page_start=1,
            page_end=1,
            order_index=0,
            is_leaf=True,
            extraction_method="ocr_scan",
        )
    ]
    pages = [
        ExtractedPage(
            page_number=1,
            width=PAGE_DEFAULT_WIDTH,
            height=PAGE_DEFAULT_HEIGHT,
            ocr_used=True,
            ocr_confidence=mean_conf,
            ocr_low_quality=is_low_quality,
            blocks=blocks,
        )
    ]

    return ExtractedDocument(
        page_count=1,
        pdf_metadata={"format": "image_ocr", "filename": filename, "ocr_mean_confidence": mean_conf},
        sections=sections,
        pages=pages,
        ocr_pages=1,
        low_quality_ocr_pages=[1] if is_low_quality else [],
        toc_extraction_method="ocr_scan",
    )


# ---------------------------------------------------------------------------
# 10. Universal Document Parser (Router)
# ---------------------------------------------------------------------------
class UniversalDocumentParser:
    """Dispatches raw document bytes to format-specific parsers based on extension."""

    SUPPORTED_EXTENSIONS = {
        ".pdf": "PDF Report",
        ".docx": "Word Document",
        ".pptx": "PowerPoint Presentation",
        ".txt": "Plain Text",
        ".md": "Markdown Document",
        ".html": "HTML Document",
        ".htm": "HTML Document",
        ".csv": "CSV Spreadsheet",
        ".xlsx": "Excel Spreadsheet",
        ".xml": "XML Data",
        ".png": "PNG Image (OCR)",
        ".jpg": "JPEG Image (OCR)",
        ".jpeg": "JPEG Image (OCR)",
        ".tiff": "TIFF Scan (OCR)",
        ".tif": "TIFF Scan (OCR)",
    }

    @classmethod
    def is_supported(cls, filename: str) -> bool:
        ext = Path(filename).suffix.lower()
        return ext in cls.SUPPORTED_EXTENSIONS

    @classmethod
    def extract(cls, raw_bytes: bytes, filename: str) -> ExtractedDocument:
        ext = Path(filename).suffix.lower()
        if ext == ".pdf":
            # Extract PDF directly in-memory via PyMuPDF without disk I/O
            return extract_pdf(raw_bytes)
        elif ext in (".txt",):
            return parse_text(raw_bytes, filename)
        elif ext in (".md",):
            return parse_markdown(raw_bytes, filename)
        elif ext in (".html", ".htm"):
            return parse_html(raw_bytes, filename)
        elif ext in (".docx",):
            return parse_docx(raw_bytes, filename)
        elif ext in (".pptx",):
            return parse_pptx(raw_bytes, filename)
        elif ext in (".csv",):
            return parse_csv(raw_bytes, filename)
        elif ext in (".xlsx",):
            return parse_xlsx(raw_bytes, filename)
        elif ext in (".xml",):
            return parse_xml(raw_bytes, filename)
        elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".tif"):
            return parse_image(raw_bytes, filename)
        else:
            raise ApiError(
                "UNSUPPORTED_FORMAT",
                f"File format '{ext}' is not supported. Supported: {', '.join(cls.SUPPORTED_EXTENSIONS.keys())}",
                status_code=415,
            )
