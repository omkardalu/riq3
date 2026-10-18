"""Text extraction from PDF and DOCX files. Never guesses: failures and unsupported inputs are reported."""
from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("riq.extract")

MAX_PDF_PAGES = 30
MAX_TEXT_CHARS = 200_000
MIN_TEXT_CHARS = 30  # fewer readable characters than this means "no usable text layer"

STATUS_OK, STATUS_EMPTY, STATUS_SCANNED, STATUS_FAILED = "ok", "empty", "scanned", "failed"

MESSAGES = {
    STATUS_SCANNED: "This PDF has no selectable text (it looks like a scanned image). OCR is not supported yet, so it cannot be analyzed.",
    STATUS_EMPTY: "This document contains no readable text.",
}


@dataclass
class Extraction:
    status: str
    text: str = ""
    pages: int | None = None
    error: str | None = None


def _readable_len(text: str) -> int:
    return sum(1 for c in text if not c.isspace())


def _classify(text: str, pages: int | None, is_pdf: bool) -> Extraction:
    text = text[:MAX_TEXT_CHARS]
    if _readable_len(text) < MIN_TEXT_CHARS:
        status = STATUS_SCANNED if is_pdf and pages else STATUS_EMPTY
        return Extraction(status, "", pages, MESSAGES[status])
    return Extraction(STATUS_OK, text, pages)


def extract_pdf(path: Path) -> Extraction:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            reader = PdfReader(str(path), strict=False)
            if reader.is_encrypted:
                try:
                    if not reader.decrypt(""):
                        return Extraction(STATUS_FAILED, error="This PDF is password-protected.")
                except Exception:  # noqa: BLE001
                    return Extraction(STATUS_FAILED, error="This PDF is password-protected.")
            total = len(reader.pages)
            parts = []
            for page in reader.pages[:MAX_PDF_PAGES]:
                parts.append(page.extract_text() or "")
        return _classify("\n".join(parts), total, True)
    except PdfReadError:
        return Extraction(STATUS_FAILED, error="This PDF is damaged and could not be read.")
    except Exception:  # noqa: BLE001 - corrupt input must never crash the request
        log.exception("pdf extraction failed")
        return Extraction(STATUS_FAILED, error="This PDF could not be read.")


def extract_docx(path: Path) -> Extraction:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        doc = Document(str(path))
        lines: list[str] = []
        for child in doc.element.body.iterchildren():
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "p":
                lines.append(Paragraph(child, doc).text)
            elif tag == "tbl":
                for row in Table(child, doc).rows:
                    seen, cells = set(), []
                    for cell in row.cells:  # merged cells repeat; keep one copy
                        if id(cell._tc) in seen:
                            continue
                        seen.add(id(cell._tc))
                        if cell.text.strip():
                            cells.append(cell.text.strip())
                    if cells:
                        lines.append(" | ".join(cells))
        return _classify("\n".join(lines), None, False)
    except Exception:  # noqa: BLE001
        log.exception("docx extraction failed")
        return Extraction(STATUS_FAILED, error="This DOCX file could not be read.")


def extract(path: Path, ext: str) -> Extraction:
    if ext == "pdf":
        return extract_pdf(path)
    if ext == "docx":
        return extract_docx(path)
    return Extraction(STATUS_FAILED, error="Unsupported file type.")
