"""Pluggable AI backend: embeddings and generation.

The default backend is fully offline and deterministic so the platform runs
with zero external dependencies or API keys. Cloud providers (OpenAI,
Anthropic) can be selected via ``IKI_AI_PROVIDER``.
"""
from .embeddings import Embedder, get_embedder
from .llm import Generator, get_generator

__all__ = ["Embedder", "get_embedder", "Generator", "get_generator"]
