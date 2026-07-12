"""The Expert Knowledge Copilot -- RAG orchestration.

Given a natural-language question it retrieves the most relevant passages from
the knowledge store, generates a grounded answer, and returns source
citations, a confidence score and direct links to the originating documents.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional, Tuple

from ..ai.embeddings import tokenize
from ..ai.llm import Generator, get_generator
from ..config import settings
from ..models import Citation, CopilotAnswer, DocType
from ..store import KnowledgeStore, ScoredChunk

# Small stopword set so "coverage" reflects content words, not glue words.
_STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are",
    "what", "why", "how", "when", "where", "which", "does", "do", "did", "with",
    "that", "this", "it", "be", "by", "at", "from", "as", "any", "can", "could",
    "should", "would", "i", "we", "you", "my", "our", "about", "into", "keep",
    "keeps", "get", "gets",
}


def _content_terms(text: str) -> set:
    return {t for t in tokenize(text) if t not in _STOPWORDS and len(t) >= 3}


def _snippet(text: str, max_len: int = 240) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= max_len else text[:max_len].rsplit(" ", 1)[0] + "..."


def _confidence(query: str, results: List[ScoredChunk]) -> Tuple[float, str]:
    """Derive a 0..1 confidence from ABSOLUTE retrieval signals.

    The blended store score is normalised to the top hit (good for ranking,
    useless as an absolute confidence). So we instead combine:
      * semantic   - raw cosine of the best hit
      * coverage   - fraction of query content-terms found in the top passages
      * corroboration - how many passages independently support the answer
    """
    if not results:
        return 0.0, "none"
    top = results[0]
    semantic = max(0.0, min(1.0, top.vector_score))

    q_terms = _content_terms(query)
    if q_terms:
        corpus = " ".join(r.chunk.text for r in results[:3])
        found_set = set(tokenize(corpus))
        coverage = sum(1 for t in q_terms if t in found_set) / len(q_terms)
    else:
        coverage = semantic

    strong = sum(1 for r in results if r.lexical_score >= 0.5 * (top.lexical_score or 1e-9))
    corroboration = min(1.0, strong / 3.0)

    confidence = 0.55 * coverage + 0.30 * semantic + 0.15 * corroboration
    confidence = round(max(0.0, min(1.0, confidence)), 3)
    if confidence >= 0.55:
        label = "high"
    elif confidence >= 0.30:
        label = "medium"
    else:
        label = "low"
    return confidence, label


# Heuristic next-best-actions surfaced to the user (agentic hooks).
_ACTION_RULES = [
    (re.compile(r"\b(leak|vibration|trip|fail|failure|breakdown|overheat|alarm|fault)\b", re.I),
     "Raise a maintenance work order referencing the cited equipment tag."),
    (re.compile(r"\b(inspect|inspection|thickness|corrosion|ndt|due)\b", re.I),
     "Check the inspection schedule and log findings against the asset register."),
    (re.compile(r"\b(permit|lockout|loto|isolation|safety|hazard|ppe)\b", re.I),
     "Confirm a valid permit-to-work and isolation before proceeding."),
    (re.compile(r"\b(start ?up|shutdown|commission|setpoint|operate|operating)\b", re.I),
     "Verify the current operating procedure revision before execution."),
    (re.compile(r"\b(regulat|statutory|compliance|emission|consent|audit)\b", re.I),
     "Cross-check the latest statutory submission and renewal dates."),
]


class Copilot:
    def __init__(self, store: KnowledgeStore, generator: Optional[Generator] = None):
        self.store = store
        self.generator = generator or get_generator()

    def answer(
        self,
        query: str,
        top_k: Optional[int] = None,
        doc_types: Optional[Iterable[DocType]] = None,
    ) -> CopilotAnswer:
        top_k = top_k or settings.top_k
        results = self.store.search(query, top_k=top_k, doc_types=doc_types)
        results = [r for r in results if r.score >= settings.min_score]

        warnings: List[str] = []
        if not results:
            return CopilotAnswer(
                query=query,
                answer=("No indexed document passages matched this question with "
                        "sufficient confidence. The answer may live in a document "
                        "that has not been ingested, or try more specific terms "
                        "(equipment tag, system name, procedure number)."),
                confidence=0.0,
                confidence_label="none",
                provider=self.generator.name,
                warnings=["No relevant context found."],
            )

        contexts: List[Tuple[int, str]] = [(i + 1, r.chunk.text) for i, r in enumerate(results)]
        answer_text = self.generator.generate(query, contexts)

        citations: List[Citation] = []
        for i, r in enumerate(results, 1):
            md = r.chunk.metadata or {}
            if md.get("loader_warnings"):
                warnings.extend(md["loader_warnings"])
            citations.append(
                Citation(
                    chunk_id=r.chunk.chunk_id,
                    doc_id=r.chunk.doc_id,
                    title=r.chunk.title,
                    doc_type=r.chunk.doc_type.value,
                    source_path=r.chunk.source_path,
                    score=round(r.score, 4),
                    snippet=_snippet(r.chunk.text),
                    metadata={k: v for k, v in md.items() if k != "loader_warnings"},
                )
            )

        confidence, label = _confidence(query, results)
        if label in ("low", "none"):
            warnings.append("Low retrieval confidence -- verify against the source document before acting.")

        suggested = self._suggest_actions(query, results)

        return CopilotAnswer(
            query=query,
            answer=answer_text,
            confidence=confidence,
            confidence_label=label,
            citations=citations,
            provider=self.generator.name,
            warnings=sorted(set(warnings)),
            suggested_actions=suggested,
        )

    def _suggest_actions(self, query: str, results: List[ScoredChunk]) -> List[str]:
        actions: List[str] = []
        haystack = query + " " + " ".join(r.chunk.text for r in results[:2])
        for pattern, action in _ACTION_RULES:
            if pattern.search(haystack) and action not in actions:
                actions.append(action)
        return actions[:3]

    def equipment_brief(self, tag: str) -> dict:
        graph_info = self.store.graph.summary(tag)
        if graph_info["mention_count"] == 0:
            return {**graph_info, "answer": None}
        ans = self.answer(f"Summarize everything known about {tag}: history, procedures, and related equipment.")
        return {**graph_info, "answer": ans.to_dict()}