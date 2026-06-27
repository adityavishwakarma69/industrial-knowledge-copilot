"""Embedding backends.

* ``HashingEmbedder`` (default) — deterministic, dependency-free vectoriser
  using hashed token unigrams + bigrams + character n-grams with sublinear
  term-frequency weighting and L2 normalisation. Good enough for strong
  cosine retrieval without any model download or API key.
* ``OpenAIEmbedder`` — wraps the OpenAI embeddings API when selected.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import List, Sequence

from ..config import settings

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[-/][A-Za-z0-9]+)*")


def tokenize(text: str) -> List[str]:
    """Lowercase tokeniser that preserves equipment-tag structure (P-101A)."""
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _hash_bucket(feature: str, dim: int) -> int:
    h = hashlib.md5(feature.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") % dim


def _hash_sign(feature: str) -> float:
    # Signed hashing reduces collision bias (a la the hashing trick).
    h = hashlib.md5((feature + "#sign").encode("utf-8")).digest()
    return 1.0 if (h[0] & 1) else -1.0


class Embedder:
    """Abstract embedder interface."""

    dim: int
    name: str = "embedder"

    def embed(self, text: str) -> List[float]:  # pragma: no cover - interface
        raise NotImplementedError

    def embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        return [self.embed(t) for t in texts]


class HashingEmbedder(Embedder):
    """Offline, deterministic hashing vectoriser."""

    name = "offline-hashing"

    def __init__(self, dim: int | None = None):
        self.dim = dim or settings.embedding_dim

    def _features(self, text: str) -> List[str]:
        tokens = tokenize(text)
        feats: List[str] = list(tokens)
        # Word bigrams capture short phrases ("work order", "cooling water").
        feats.extend(f"{a}_{b}" for a, b in zip(tokens, tokens[1:]))
        # Character trigrams on longer tokens add fuzzy/robust matching.
        for tok in tokens:
            if len(tok) >= 6:
                feats.extend(f"#{tok[i:i+3]}" for i in range(len(tok) - 2))
        return feats

    def embed(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        counts: dict[str, int] = {}
        for feat in self._features(text):
            counts[feat] = counts.get(feat, 0) + 1
        for feat, cnt in counts.items():
            weight = (1.0 + math.log(cnt)) * _hash_sign(feat)  # sublinear TF
            vec[_hash_bucket(feat, self.dim)] += weight
        # L2 normalise so dot product == cosine similarity.
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


class OpenAIEmbedder(Embedder):
    """Embeddings via the OpenAI API (requires OPENAI_API_KEY)."""

    name = "openai"

    def __init__(self, model: str | None = None):
        from openai import OpenAI  # imported lazily

        self._client = OpenAI()
        self.model = model or settings.embedding_model
        # Dimensions per model; text-embedding-3-* default sizes.
        self.dim = 1536

    def embed(self, text: str) -> List[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        resp = self._client.embeddings.create(model=self.model, input=list(texts))
        return [d.embedding for d in resp.data]


def get_embedder() -> Embedder:
    """Factory honouring IKI_AI_PROVIDER, with safe fallback to offline."""
    provider = settings.ai_provider.lower()
    if provider == "openai":
        try:
            return OpenAIEmbedder()
        except Exception as exc:  # missing key / package -> fallback
            print(f"[iki] OpenAI embedder unavailable ({exc}); using offline embedder.")
    # Anthropic has no public embeddings endpoint -> offline embeddings,
    # Anthropic is still used for generation (see llm.py).
    return HashingEmbedder()
