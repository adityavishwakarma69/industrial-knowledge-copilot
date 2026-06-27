"""Core data models shared across the platform."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class DocType(str, Enum):
    """Heterogeneous industrial document categories."""

    ENGINEERING_DRAWING = "engineering_drawing"   # P&IDs, GA drawings, isometrics
    MAINTENANCE_RECORD = "maintenance_record"     # work orders, breakdown logs
    SAFETY_PROCEDURE = "safety_procedure"         # SOPs, JSAs, permits to work
    INSPECTION_REPORT = "inspection_report"       # NDT, thickness surveys
    OPERATING_INSTRUCTION = "operating_instruction"
    PROJECT_FILE = "project_file"                 # commissioning, MoC, handover
    REGULATORY_SUBMISSION = "regulatory_submission"
    OTHER = "other"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Document:
    """A source document before chunking."""

    doc_id: str
    title: str
    doc_type: DocType
    source_path: str
    text: str
    # Free-form metadata: equipment tag, plant area, author, date, criticality...
    metadata: Dict[str, Any] = field(default_factory=dict)
    ingested_at: str = field(default_factory=_now)

    @staticmethod
    def make_id(source_path: str, title: str) -> str:
        return "doc_" + hashlib.sha1(f"{source_path}|{title}".encode("utf-8")).hexdigest()[:12]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["doc_type"] = self.doc_type.value
        return d


@dataclass
class Chunk:
    """A retrievable unit of text with a back-reference to its document."""

    chunk_id: str
    doc_id: str
    title: str
    doc_type: DocType
    source_path: str
    text: str
    seq: int                      # position within the document
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None

    def to_dict(self, include_embedding: bool = True) -> Dict[str, Any]:
        d = asdict(self)
        d["doc_type"] = self.doc_type.value
        if not include_embedding:
            d.pop("embedding", None)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Chunk":
        d = dict(d)
        d["doc_type"] = DocType(d["doc_type"])
        return cls(**d)


@dataclass
class Citation:
    """A grounding reference returned alongside an answer."""

    chunk_id: str
    doc_id: str
    title: str
    doc_type: str
    source_path: str
    score: float
    snippet: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CopilotAnswer:
    """The full response from the Expert Knowledge Copilot."""

    query: str
    answer: str
    confidence: float                       # 0..1
    confidence_label: str                   # high / medium / low
    citations: List[Citation] = field(default_factory=list)
    provider: str = "offline"
    warnings: List[str] = field(default_factory=list)
    suggested_actions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "answer": self.answer,
            "confidence": round(self.confidence, 3),
            "confidence_label": self.confidence_label,
            "citations": [c.to_dict() for c in self.citations],
            "provider": self.provider,
            "warnings": self.warnings,
            "suggested_actions": self.suggested_actions,
        }
