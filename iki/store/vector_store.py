"""A lightweight persistent knowledge store with hybrid (vector + lexical) search.

The store keeps document metadata plus per-chunk embeddings on disk as JSON so
the demo has no external database dependency. Search blends dense cosine
similarity with a BM25-style lexical score, which makes the offline backend
robust for exact equipment-tag / part-number lookups as well as semantic
queries.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from ..config import settings
from ..models import Chunk, Document, DocType
from ..ai.embeddings import Embedder, get_embedder, tokenize
from ..graph import EquipmentGraph


@dataclass
class ScoredChunk:
    chunk: Chunk
    score: float          # blended final score (0..1-ish)
    vector_score: float
    lexical_score: float


class KnowledgeStore:
    def __init__(self, embedder: Optional[Embedder] = None, path: Optional[Path] = None):
        self.embedder = embedder or get_embedder()
        self.path = Path(path) if path else settings.index_path
        self.graph = EquipmentGraph()
        self.documents: Dict[str, dict] = {}
        self.chunks: List[Chunk] = []
        self._df: Dict[str, int] = {}            # document (chunk) frequency
        self._chunk_tokens: List[set] = []       # cached token sets per chunk
        self._avg_len: float = 0.0
        

    # ------------------------------------------------------------------ #
    # Mutation
    # ------------------------------------------------------------------ #
    def add_document(self, doc: Document, chunks: List[Chunk]) -> None:
        # Replace any existing version of this document.
        if doc.doc_id in self.documents:
            self.remove_document(doc.doc_id)

        self.documents[doc.doc_id] = doc.to_dict()
        texts = [c.text for c in chunks]
        embeddings = self.embedder.embed_batch(texts)
        for chunk, emb in zip(chunks, embeddings):
            chunk.embedding = emb
            self.chunks.append(chunk)
        self._reindex_lexical()

    def remove_document(self, doc_id: str) -> int:
        before = len(self.chunks)
        self.chunks = [c for c in self.chunks if c.doc_id != doc_id]
        self.documents.pop(doc_id, None)
        removed = before - len(self.chunks)
        if removed:
            self._reindex_lexical()
        return removed

    def clear(self) -> None:
        self.documents.clear()
        self.chunks.clear()
        self._df.clear()
        self._chunk_tokens.clear()
        self._avg_len = 0.0

    # ------------------------------------------------------------------ #
    # Lexical index
    # ------------------------------------------------------------------ #
    def _reindex_lexical(self) -> None:
        self._df.clear()
        self._chunk_tokens = []
        total_len = 0
        for chunk in self.chunks:
            toks = tokenize(chunk.text)
            tokset = set(toks)
            self._chunk_tokens.append(tokset)
            total_len += len(toks)
            for t in tokset:
                self._df[t] = self._df.get(t, 0) + 1
        self._avg_len = (total_len / len(self.chunks)) if self.chunks else 0.0
        self.graph.build(self.chunks)

    def _idf(self, term: str) -> float:
        n = len(self.chunks)
        df = self._df.get(term, 0)
        if df == 0:
            return 0.0
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def _bm25(self, q_tokens: List[str], idx: int, k1: float = 1.5, b: float = 0.75) -> float:
        chunk = self.chunks[idx]
        doc_tokens = tokenize(chunk.text)
        dl = len(doc_tokens) or 1
        tf: Dict[str, int] = {}
        for t in doc_tokens:
            tf[t] = tf.get(t, 0) + 1
        score = 0.0
        for term in q_tokens:
            if term not in tf:
                continue
            idf = self._idf(term)
            freq = tf[term]
            denom = freq + k1 * (1 - b + b * dl / (self._avg_len or 1))
            score += idf * (freq * (k1 + 1)) / (denom or 1)
        return score

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #
    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        # Embeddings are L2-normalised, so dot product == cosine.
        return sum(x * y for x, y in zip(a, b))

    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        doc_types: Optional[Iterable[DocType]] = None,
        alpha: float = 0.6,
    ) -> List[ScoredChunk]:
        """Hybrid search. ``alpha`` weights vector vs lexical (0..1)."""
        if not self.chunks:
            return []
        top_k = top_k or settings.top_k
        type_filter = {dt.value if isinstance(dt, DocType) else dt for dt in doc_types} if doc_types else None

        q_emb = self.embedder.embed(query)
        q_tokens = tokenize(query)

        vec_scores: List[float] = []
        lex_scores: List[float] = []
        for idx, chunk in enumerate(self.chunks):
            if type_filter and chunk.doc_type.value not in type_filter:
                vec_scores.append(0.0)
                lex_scores.append(0.0)
                continue
            vec_scores.append(self._cosine(q_emb, chunk.embedding or []))
            lex_scores.append(self._bm25(q_tokens, idx))

        max_lex = max(lex_scores) or 1.0
        max_vec = max(vec_scores) or 1.0
        results: List[ScoredChunk] = []
        for idx, chunk in enumerate(self.chunks):
            if type_filter and chunk.doc_type.value not in type_filter:
                continue
            v = vec_scores[idx] / max_vec if max_vec else 0.0
            l = lex_scores[idx] / max_lex if max_lex else 0.0
            blended = alpha * v + (1 - alpha) * l
            if blended <= 0:
                continue
            results.append(ScoredChunk(chunk=chunk, score=blended,
                                       vector_score=vec_scores[idx],
                                       lexical_score=lex_scores[idx]))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    # ------------------------------------------------------------------ #
    # Stats
    # ------------------------------------------------------------------ #
    def stats(self) -> dict:
        by_type: Dict[str, int] = {}
        for d in self.documents.values():
            by_type[d["doc_type"]] = by_type.get(d["doc_type"], 0) + 1
        return {
            "documents": len(self.documents),
            "chunks": len(self.chunks),
            "documents_by_type": by_type,
            "embedder": self.embedder.name,
            "embedding_dim": getattr(self.embedder, "dim", None),
        }

    def list_documents(self) -> List[dict]:
        out = []
        for doc_id, d in self.documents.items():
            n_chunks = sum(1 for c in self.chunks if c.doc_id == doc_id)
            out.append({
                "doc_id": doc_id,
                "title": d["title"],
                "doc_type": d["doc_type"],
                "source_path": d["source_path"],
                "chunks": n_chunks,
                "metadata": d.get("metadata", {}),
            })
        return sorted(out, key=lambda x: (x["doc_type"], x["title"]))

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def save(self, path: Optional[Path] = None) -> Path:
        path = Path(path) if path else self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "embedder": self.embedder.name,
            "embedding_dim": getattr(self.embedder, "dim", None),
            "documents": self.documents,
            "chunks": [c.to_dict(include_embedding=True) for c in self.chunks],
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def load(self, path: Optional[Path] = None) -> bool:
        path = Path(path) if path else self.path
        if not path.exists():
            return False
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.documents = payload.get("documents", {})
        self.chunks = [Chunk.from_dict(c) for c in payload.get("chunks", [])]
        self._reindex_lexical()
        return True

    @classmethod
    def open(cls, path: Optional[Path] = None, embedder: Optional[Embedder] = None) -> "KnowledgeStore":
        store = cls(embedder=embedder, path=path)
        store.load()
        return store
