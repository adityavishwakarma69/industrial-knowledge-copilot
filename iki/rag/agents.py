"""Agentic helpers for maintenance and compliance workflows.

These compose multiple retrieval passes over the corpus to answer
multi-step operational questions that a single query cannot — for example
assembling an equipment's failure history, related procedures and open
inspection actions into one briefing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..models import CopilotAnswer, DocType
from ..store import KnowledgeStore
from .copilot import Copilot

_TAG_RE = re.compile(r"\b[A-Z]{1,4}-?\d{2,4}[A-Z]?\b")


@dataclass
class AgentBriefing:
    subject: str
    sections: Dict[str, CopilotAnswer] = field(default_factory=dict)
    related_documents: List[dict] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "sections": {k: v.to_dict() for k, v in self.sections.items()},
            "related_documents": self.related_documents,
            "flags": self.flags,
        }


class _BaseAgent:
    def __init__(self, store: KnowledgeStore, copilot: Optional[Copilot] = None):
        self.store = store
        self.copilot = copilot or Copilot(store)

    def _related_docs(self, term: str, limit: int = 8) -> List[dict]:
        results = self.store.search(term, top_k=limit)
        seen: Dict[str, dict] = {}
        for r in results:
            seen.setdefault(r.chunk.doc_id, {
                "doc_id": r.chunk.doc_id,
                "title": r.chunk.title,
                "doc_type": r.chunk.doc_type.value,
                "source_path": r.chunk.source_path,
                "score": round(r.score, 3),
            })
        return list(seen.values())


class MaintenanceAgent(_BaseAgent):
    """Assembles a maintenance briefing for a piece of equipment."""

    def diagnose(self, equipment: str) -> AgentBriefing:
        briefing = AgentBriefing(subject=f"Maintenance briefing: {equipment}")
        briefing.sections["failure_history"] = self.copilot.answer(
            f"What failures, breakdowns or repairs are recorded for {equipment}?",
            doc_types=[DocType.MAINTENANCE_RECORD],
        )
        briefing.sections["failure_patterns"] = self.copilot.answer(
            f"What are the recurring failure modes or root causes for {equipment}?",
        )
        briefing.sections["procedures"] = self.copilot.answer(
            f"What operating and safety procedures apply when working on {equipment}?",
            doc_types=[DocType.SAFETY_PROCEDURE, DocType.OPERATING_INSTRUCTION],
        )
        briefing.sections["inspection"] = self.copilot.answer(
            f"What inspection findings or due dates exist for {equipment}?",
            doc_types=[DocType.INSPECTION_REPORT],
        )
        briefing.related_documents = self._related_docs(equipment)

        # Simple risk flags from the assembled evidence.
        hist = briefing.sections["failure_history"].answer.lower()
        if any(w in hist for w in ("recurring", "repeated", "again", "third time", "frequent")):
            briefing.flags.append("Possible recurring failure — consider root-cause analysis.")
        if briefing.sections["inspection"].confidence_label in ("low", "none"):
            briefing.flags.append("No recent inspection record found — verify inspection status.")
        return briefing


class ComplianceAgent(_BaseAgent):
    """Checks whether a procedure/initiative is supported by required documents."""

    REQUIRED = {
        "safety procedure": DocType.SAFETY_PROCEDURE,
        "operating instruction": DocType.OPERATING_INSTRUCTION,
        "inspection record": DocType.INSPECTION_REPORT,
        "regulatory submission": DocType.REGULATORY_SUBMISSION,
    }

    def check(self, topic: str) -> AgentBriefing:
        briefing = AgentBriefing(subject=f"Compliance check: {topic}")
        briefing.sections["overview"] = self.copilot.answer(
            f"What compliance, safety and regulatory requirements apply to {topic}?",
        )
        # Gap analysis: is each required document class represented?
        for label, dtype in self.REQUIRED.items():
            ans = self.copilot.answer(
                f"What {label} covers {topic}?", doc_types=[dtype], top_k=3,
            )
            briefing.sections[label.replace(" ", "_")] = ans
            if ans.confidence_label in ("low", "none"):
                briefing.flags.append(f"Gap: no clear {label} found for '{topic}'.")
        briefing.related_documents = self._related_docs(topic)
        if not briefing.flags:
            briefing.flags.append("All required document classes are represented in the corpus.")
        return briefing
