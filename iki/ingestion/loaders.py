"""Loaders for heterogeneous document formats.

Each loader returns a list of ``Document`` objects. Loaders degrade
gracefully: if an optional dependency (e.g. ``pypdf``) is unavailable, the
loader records a warning in metadata rather than crashing the pipeline.
"""
from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models import Document, DocType

# --------------------------------------------------------------------------- #
# Document-type inference
# --------------------------------------------------------------------------- #

# Keyword heuristics used when a document does not declare its own type.
_TYPE_KEYWORDS = {
    DocType.ENGINEERING_DRAWING: ["p&id", "pid", "piping and instrumentation", "isometric",
                                  "general arrangement", "ga drawing", "datasheet", "loop diagram"],
    DocType.MAINTENANCE_RECORD: ["work order", "breakdown", "maintenance", "repair", "cmms",
                                 "preventive", "lubrication", "spare part"],
    DocType.SAFETY_PROCEDURE: ["sop", "standard operating procedure", "permit to work", "jsa",
                               "lockout", "tagout", "loto", "hazard", "ppe", "safety"],
    DocType.INSPECTION_REPORT: ["inspection", "ndt", "thickness", "ut survey", "corrosion",
                                "ultrasonic", "radiograph", "visual examination"],
    DocType.OPERATING_INSTRUCTION: ["operating instruction", "operation manual", "startup",
                                    "shutdown", "operating procedure", "setpoint"],
    DocType.REGULATORY_SUBMISSION: ["regulatory", "compliance", "statutory", "peso", "factory act",
                                    "pollution control", "emission", "consent to operate"],
    DocType.PROJECT_FILE: ["commissioning", "management of change", "moc", "handover",
                           "project", "punch list", "fat", "sat"],
}


def infer_doc_type(text: str, filename: str = "") -> DocType:
    """Best-effort classification from filename + content keywords."""
    haystack = (filename + "\n" + text[:2000]).lower()
    best_type = DocType.OTHER
    best_hits = 0
    for dtype, keywords in _TYPE_KEYWORDS.items():
        hits = sum(haystack.count(k) for k in keywords)
        if hits > best_hits:
            best_hits = hits
            best_type = dtype
    return best_type


# --------------------------------------------------------------------------- #
# Lightweight front-matter parsing
# --------------------------------------------------------------------------- #

_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_front_matter(text: str) -> tuple[Dict[str, Any], str]:
    """Parse an optional ``--- key: value ---`` block at the top of a text file."""
    m = _FRONT_MATTER_RE.match(text)
    if not m:
        return {}, text
    meta: Dict[str, Any] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta, text[m.end():]


def _extract_equipment_tags(text: str) -> List[str]:
    """Detect ISA-style equipment / instrument tags (e.g. P-101A, FT-2301, HX-12)."""
    tags = re.findall(r"\b[A-Z]{1,4}-?\d{2,4}[A-Z]?\b", text)
    # De-duplicate while preserving order.
    seen: Dict[str, None] = {}
    for t in tags:
        seen.setdefault(t, None)
    return list(seen.keys())[:40]


def _finalise(doc: Document) -> Document:
    """Enrich a freshly-loaded document with derived metadata."""
    if doc.doc_type == DocType.OTHER:
        doc.doc_type = infer_doc_type(doc.text, doc.title)
    tags = _extract_equipment_tags(doc.text)
    if tags:
        doc.metadata.setdefault("equipment_tags", tags)
    doc.metadata.setdefault("char_count", len(doc.text))
    return doc


# --------------------------------------------------------------------------- #
# Format-specific loaders
# --------------------------------------------------------------------------- #

def load_text(path: Path) -> Document:
    raw = path.read_text(encoding="utf-8", errors="replace")
    meta, body = _parse_front_matter(raw)
    declared_type = meta.pop("doc_type", None)
    doc_type = DocType(declared_type) if declared_type in DocType._value2member_map_ else DocType.OTHER
    title = meta.pop("title", path.stem.replace("_", " ").title())
    doc = Document(
        doc_id=Document.make_id(str(path), title),
        title=title,
        doc_type=doc_type,
        source_path=str(path),
        text=body.strip(),
        metadata={k: v for k, v in meta.items()},
    )
    return _finalise(doc)


def load_csv(path: Path) -> Document:
    """Flatten a CSV (e.g. a CMMS work-order export) into readable text."""
    rows: List[Dict[str, str]] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append({(k or "").strip(): (v or "").strip() for k, v in row.items()})

    lines: List[str] = []
    for i, row in enumerate(rows, 1):
        parts = [f"{k}: {v}" for k, v in row.items() if v]
        lines.append(f"Record {i} — " + "; ".join(parts))
    body = "\n".join(lines)
    title = path.stem.replace("_", " ").title()
    doc = Document(
        doc_id=Document.make_id(str(path), title),
        title=title,
        doc_type=DocType.OTHER,
        source_path=str(path),
        text=body,
        metadata={"record_count": len(rows), "columns": list(rows[0].keys()) if rows else []},
    )
    return _finalise(doc)


def load_json_drawing(path: Path) -> Document:
    """Load a structured drawing / P&ID digitisation sidecar.

    Expected (flexible) shape::

        {
          "title": "P&ID - Cooling Water Circuit",
          "doc_type": "engineering_drawing",
          "drawing_no": "PID-CW-001",
          "equipment": [{"tag": "P-101A", "desc": "CW Pump A", "type": "centrifugal pump"}],
          "lines": [{"id": "CW-6-101", "from": "T-100", "to": "P-101A", "service": "cooling water"}],
          "instruments": [{"tag": "FT-2301", "desc": "CW flow transmitter"}],
          "notes": "..."
        }
    """
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    title = data.get("title", path.stem.replace("_", " ").title())

    segments: List[str] = []
    if data.get("drawing_no"):
        segments.append(f"Drawing number: {data['drawing_no']}.")
    if data.get("description"):
        segments.append(str(data["description"]))

    for eq in data.get("equipment", []):
        segments.append(
            f"Equipment {eq.get('tag', '?')}: {eq.get('desc', '')} "
            f"({eq.get('type', '')}). " + _kv_tail(eq, skip={"tag", "desc", "type"})
        )
    for ln in data.get("lines", []):
        segments.append(
            f"Process line {ln.get('id', '?')} carries {ln.get('service', 'process fluid')} "
            f"from {ln.get('from', '?')} to {ln.get('to', '?')}."
        )
    for inst in data.get("instruments", []):
        segments.append(
            f"Instrument {inst.get('tag', '?')}: {inst.get('desc', '')}. "
            + _kv_tail(inst, skip={"tag", "desc"})
        )
    if data.get("notes"):
        segments.append("Notes: " + str(data["notes"]))

    body = "\n".join(s.strip() for s in segments if s.strip())
    declared = data.get("doc_type", "engineering_drawing")
    doc_type = DocType(declared) if declared in DocType._value2member_map_ else DocType.ENGINEERING_DRAWING
    meta = {k: v for k, v in data.items()
            if k not in {"title", "doc_type", "description", "notes"}}
    doc = Document(
        doc_id=Document.make_id(str(path), title),
        title=title,
        doc_type=doc_type,
        source_path=str(path),
        text=body,
        metadata=meta,
    )
    return _finalise(doc)


def _kv_tail(d: Dict[str, Any], skip: set) -> str:
    extra = [f"{k}={v}" for k, v in d.items() if k not in skip and v not in (None, "")]
    return ("(" + ", ".join(extra) + ")") if extra else ""


def load_pdf(path: Path) -> Document:
    """Extract text from a PDF. Falls back gracefully if pypdf is missing."""
    title = path.stem.replace("_", " ").title()
    warnings: List[str] = []
    text = ""
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        text = "\n\n".join(pages).strip()
        if not text:
            warnings.append("PDF produced no extractable text (likely scanned — OCR required).")
    except ImportError:
        warnings.append("pypdf not installed; PDF text could not be extracted.")
    except Exception as exc:  # pragma: no cover - defensive
        warnings.append(f"PDF extraction failed: {exc}")

    doc = Document(
        doc_id=Document.make_id(str(path), title),
        title=title,
        doc_type=DocType.OTHER,
        source_path=str(path),
        text=text,
        metadata={"loader_warnings": warnings} if warnings else {},
    )
    return _finalise(doc)


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #

_SUFFIX_LOADERS = {
    ".txt": load_text,
    ".md": load_text,
    ".csv": load_csv,
    ".json": load_json_drawing,
    ".pdf": load_pdf,
}

SUPPORTED_SUFFIXES = set(_SUFFIX_LOADERS.keys())


def load_file(path: Path) -> Optional[Document]:
    """Load a single file, dispatching on extension. Returns None if unsupported."""
    loader = _SUFFIX_LOADERS.get(path.suffix.lower())
    if loader is None:
        return None
    return loader(path)


def make_inline_document(
    title: str,
    text: str,
    doc_type: DocType = DocType.OTHER,
    source_path: str = "inline",
    metadata: Optional[Dict[str, Any]] = None,
) -> Document:
    """Build a Document from raw in-memory text (e.g. an API upload)."""
    doc = Document(
        doc_id=Document.make_id(source_path, title),
        title=title,
        doc_type=doc_type,
        source_path=source_path,
        text=text.strip(),
        metadata=metadata or {},
    )
    return _finalise(doc)
