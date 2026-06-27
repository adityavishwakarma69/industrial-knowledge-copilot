"""The ingestion pipeline: load -> chunk -> embed -> store."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..models import Document
from .chunker import chunk_document
from .loaders import SUPPORTED_SUFFIXES, load_file, make_inline_document


@dataclass
class IngestionResult:
    documents: int = 0
    chunks: int = 0
    skipped: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    doc_ids: List[str] = field(default_factory=list)

    def merge(self, other: "IngestionResult") -> None:
        self.documents += other.documents
        self.chunks += other.chunks
        self.skipped.extend(other.skipped)
        self.warnings.extend(other.warnings)
        self.doc_ids.extend(other.doc_ids)

    def to_dict(self) -> dict:
        return {
            "documents": self.documents,
            "chunks": self.chunks,
            "skipped": self.skipped,
            "warnings": self.warnings,
            "doc_ids": self.doc_ids,
        }


class IngestionPipeline:
    """Coordinates loading, chunking and storage of documents."""

    def __init__(self, store):
        # ``store`` is an iki.store.KnowledgeStore (duck-typed to avoid a
        # hard import cycle).
        self.store = store

    def ingest_document(self, doc: Document) -> IngestionResult:
        result = IngestionResult()
        warnings = doc.metadata.get("loader_warnings", [])
        if warnings:
            result.warnings.extend(f"[{doc.title}] {w}" for w in warnings)
        chunks = chunk_document(doc)
        if not chunks:
            result.skipped.append(f"{doc.title} (no extractable text)")
            return result
        self.store.add_document(doc, chunks)
        result.documents = 1
        result.chunks = len(chunks)
        result.doc_ids.append(doc.doc_id)
        return result

    def ingest_file(self, path: Path) -> IngestionResult:
        result = IngestionResult()
        doc = load_file(path)
        if doc is None:
            result.skipped.append(f"{path.name} (unsupported type)")
            return result
        return self.ingest_document(doc)

    def ingest_directory(self, directory: Path, recursive: bool = True) -> IngestionResult:
        result = IngestionResult()
        pattern = "**/*" if recursive else "*"
        for path in sorted(directory.glob(pattern)):
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
                result.merge(self.ingest_file(path))
        return result

    def ingest_text(self, title: str, text: str, **kwargs) -> IngestionResult:
        doc = make_inline_document(title=title, text=text, **kwargs)
        return self.ingest_document(doc)


# --------------------------------------------------------------------------- #
# Convenience helpers
# --------------------------------------------------------------------------- #

def ingest_path(store, path: str | Path, recursive: bool = True) -> IngestionResult:
    p = Path(path)
    pipeline = IngestionPipeline(store)
    if p.is_dir():
        return pipeline.ingest_directory(p, recursive=recursive)
    return pipeline.ingest_file(p)


def ingest_directory(store, directory: str | Path, recursive: bool = True) -> IngestionResult:
    return IngestionPipeline(store).ingest_directory(Path(directory), recursive=recursive)
