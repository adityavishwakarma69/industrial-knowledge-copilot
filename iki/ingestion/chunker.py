"""Sentence-aware text chunking with overlap.

Industrial documents mix prose (procedures), tabular lines (work orders) and
short tag references (drawings). We chunk on paragraph / sentence boundaries
where possible and fall back to hard splits for very long lines, keeping a
configurable character overlap so context is not lost across boundaries.
"""
from __future__ import annotations

import hashlib
import re
from typing import List

from ..config import settings
from ..models import Chunk, Document

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def _split_units(text: str) -> List[str]:
    """Break text into atomic units (paragraphs, then sentences)."""
    units: List[str] = []
    for para in re.split(r"\n{2,}", text):
        para = para.strip()
        if not para:
            continue
        # Single-line records (CSV-derived) stay whole; prose is split further.
        if "\n" in para or len(para) <= settings.chunk_size:
            units.append(para)
        else:
            units.extend(s.strip() for s in _SENT_SPLIT.split(para) if s.strip())
    return units


def _chunk_id(doc_id: str, seq: int, text: str) -> str:
    h = hashlib.sha1(f"{doc_id}|{seq}|{text[:64]}".encode("utf-8")).hexdigest()[:10]
    return f"{doc_id}::ch{seq:03d}::{h}"


def chunk_document(doc: Document,
                   chunk_size: int | None = None,
                   overlap: int | None = None) -> List[Chunk]:
    """Split a document into overlapping retrievable chunks."""
    chunk_size = chunk_size or settings.chunk_size
    overlap = overlap or settings.chunk_overlap
    if not doc.text.strip():
        return []

    units = _split_units(doc.text)
    chunks: List[Chunk] = []
    buf: List[str] = []
    buf_len = 0
    seq = 0

    def flush() -> None:
        nonlocal buf, buf_len, seq
        if not buf:
            return
        text = "\n".join(buf).strip()
        if text:
            chunks.append(
                Chunk(
                    chunk_id=_chunk_id(doc.doc_id, seq, text),
                    doc_id=doc.doc_id,
                    title=doc.title,
                    doc_type=doc.doc_type,
                    source_path=doc.source_path,
                    text=text,
                    seq=seq,
                    metadata=dict(doc.metadata),
                )
            )
            seq += 1
        # Start the next buffer with a tail overlap for context continuity.
        if overlap > 0 and text:
            tail = text[-overlap:]
            buf = [tail]
            buf_len = len(tail)
        else:
            buf = []
            buf_len = 0

    for unit in units:
        if buf_len + len(unit) + 1 > chunk_size and buf:
            flush()
        # A single unit larger than chunk_size is hard-split.
        while len(unit) > chunk_size:
            head, unit = unit[:chunk_size], unit[chunk_size - overlap:]
            buf.append(head)
            buf_len += len(head)
            flush()
        buf.append(unit)
        buf_len += len(unit) + 1

    flush()
    return chunks
