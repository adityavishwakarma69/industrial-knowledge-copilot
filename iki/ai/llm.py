"""Answer-generation backends.

* ``ExtractiveGenerator`` (default, offline) -- composes a grounded answer by
  ranking and stitching the most relevant sentences from retrieved chunks,
  with inline ``[n]`` citation markers. No model or API key required.
* ``OpenAIGenerator`` / ``AnthropicGenerator`` -- produce a synthesised,
  natural-language answer constrained to the supplied context.
"""
from __future__ import annotations

import re
from typing import List, Sequence, Tuple

from ..config import settings
from .embeddings import tokenize

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_MD_HEADER = re.compile(r"^#{1,6}\s*")
_BOILERPLATE = {"summary", "purpose and scope", "method", "findings", "conclusion",
                "scope", "overview", "records", "notes"}


def _clean_sentence(sent: str) -> str:
    """Strip markdown markers and collapse whitespace from a candidate sentence."""
    sent = sent.strip()
    lines = [_MD_HEADER.sub("", ln).lstrip("-*> ").strip() for ln in sent.splitlines()]
    sent = " ".join(ln for ln in lines if ln)
    return re.sub(r"\s+", " ", sent).strip()


SYSTEM_PROMPT = (
    "You are an Industrial Knowledge Copilot for plant operations, maintenance "
    "and engineering. Answer ONLY from the provided context passages. Cite every "
    "claim with bracketed source numbers like [1], [2]. If the context is "
    "insufficient, say so explicitly and do not invent equipment tags, values or "
    "procedures. Be concise and practical; field technicians read this on mobile."
)


class Generator:
    name = "generator"

    def generate(self, query: str, contexts: Sequence[Tuple[int, str]]) -> str:
        """``contexts`` is a list of (citation_number, passage_text)."""
        raise NotImplementedError


class ExtractiveGenerator(Generator):
    """Offline extractive answer synthesis with inline citations."""

    name = "offline-extractive"

    def __init__(self, max_sentences: int = 5):
        self.max_sentences = max_sentences

    def generate(self, query: str, contexts: Sequence[Tuple[int, str]]) -> str:
        if not contexts:
            return ("I could not find anything in the indexed documents that answers "
                    "this question. Try rephrasing, or check that the relevant "
                    "document set has been ingested.")

        q_terms = set(tokenize(query))
        scored: List[Tuple[float, int, str]] = []
        for cite_no, passage in contexts:
            # Split on lines first (records / list items), then on sentences,
            # so candidates stay short and on-point.
            candidates: List[str] = []
            for line in passage.splitlines():
                candidates.extend(_SENT_SPLIT.split(line))
            for sent in candidates:
                sent = _clean_sentence(sent)
                if len(sent) < 15:
                    continue
                if sent.lower() in _BOILERPLATE:
                    continue
                s_terms = tokenize(sent)
                if not s_terms:
                    continue
                overlap = sum(1 for t in s_terms if t in q_terms)
                score = overlap / (1.0 + 0.01 * len(s_terms))
                if overlap == 0:
                    score *= 0.15
                scored.append((score, cite_no, sent))

        scored.sort(key=lambda x: x[0], reverse=True)

        chosen: List[Tuple[int, str]] = []
        seen_text: set = set()
        for score, cite_no, sent in scored:
            key = sent[:60].lower()
            if key in seen_text:
                continue
            seen_text.add(key)
            chosen.append((cite_no, sent))
            if len(chosen) >= self.max_sentences:
                break

        if not chosen:
            cite_no, passage = contexts[0]
            return passage.strip()[:600] + f" [{cite_no}]"

        chosen.sort(key=lambda x: x[1])
        parts = []
        for cite_no, sent in chosen:
            sent = sent.rstrip(".")
            parts.append(f"{sent} [{cite_no}].")
        return " ".join(parts)


def _build_user_prompt(query: str, contexts: Sequence[Tuple[int, str]]) -> str:
    blocks = [f"[{n}] {text}" for n, text in contexts]
    joined = "\n\n".join(blocks)
    return f"CONTEXT PASSAGES:\n{joined}\n\nQUESTION: {query}\n\nGrounded answer with citations:"


class OpenAIGenerator(Generator):
    name = "openai"

    def __init__(self, model: str = None):
        from openai import OpenAI

        self._client = OpenAI()
        self.model = model or settings.generation_model

    def generate(self, query: str, contexts: Sequence[Tuple[int, str]]) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            temperature=0.1,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(query, contexts)},
            ],
        )
        return resp.choices[0].message.content.strip()


class AnthropicGenerator(Generator):
    name = "anthropic"

    def __init__(self, model: str = None):
        from anthropic import Anthropic

        self._client = Anthropic()
        self.model = model or "claude-3-5-sonnet-latest"

    def generate(self, query: str, contexts: Sequence[Tuple[int, str]]) -> str:
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=700,
            temperature=0.1,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_user_prompt(query, contexts)}],
        )
        return "".join(b.text for b in msg.content if b.type == "text").strip()


def get_generator() -> Generator:
    """Factory honouring IKI_AI_PROVIDER, with safe fallback to offline."""
    provider = settings.ai_provider.lower()
    if provider == "openai":
        try:
            return OpenAIGenerator()
        except Exception as exc:
            print(f"[iki] OpenAI generator unavailable ({exc}); using offline generator.")
    elif provider == "anthropic":
        try:
            return AnthropicGenerator()
        except Exception as exc:
            print(f"[iki] Anthropic generator unavailable ({exc}); using offline generator.")
    return ExtractiveGenerator()
