"""Knowledge store: persistent vector + lexical index over document chunks."""
from .vector_store import KnowledgeStore, ScoredChunk

__all__ = ["KnowledgeStore", "ScoredChunk"]
