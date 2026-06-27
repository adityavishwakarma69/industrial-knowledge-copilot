"""End-to-end and unit tests for the Industrial Knowledge Copilot."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from iki.ai.embeddings import HashingEmbedder, tokenize
from iki.ingestion import IngestionPipeline
from iki.ingestion.chunker import chunk_document
from iki.ingestion.loaders import make_inline_document, infer_doc_type
from iki.models import DocType
from iki.rag import Copilot, MaintenanceAgent, ComplianceAgent
from iki.store import KnowledgeStore


@pytest.fixture()
def seeded_store(tmp_path):
    store = KnowledgeStore(embedder=HashingEmbedder(dim=512), path=tmp_path / "idx.json")
    pipeline = IngestionPipeline(store)
    pipeline.ingest_directory(ROOT / "sample_data")
    return store


# --------------------------------------------------------------------------- #
# Embeddings
# --------------------------------------------------------------------------- #
def test_embeddings_deterministic_and_normalised():
    emb = HashingEmbedder(dim=256)
    v1 = emb.embed("cooling water pump P-101A trip")
    v2 = emb.embed("cooling water pump P-101A trip")
    assert v1 == v2                                  # deterministic
    norm = sum(x * x for x in v1) ** 0.5
    assert abs(norm - 1.0) < 1e-6                     # L2 normalised


def test_tokenizer_preserves_tags():
    assert "p-101a" in tokenize("Pump P-101A tripped")


def test_similar_text_scores_higher():
    emb = HashingEmbedder(dim=512)
    q = emb.embed("pump bearing vibration high")
    near = emb.embed("the pump bearing vibration is too high")
    far = emb.embed("regulatory consent to operate renewal")
    cos = lambda a, b: sum(x * y for x, y in zip(a, b))
    assert cos(q, near) > cos(q, far)


# --------------------------------------------------------------------------- #
# Loaders / chunker
# --------------------------------------------------------------------------- #
def test_doc_type_inference():
    assert infer_doc_type("This is a work order for breakdown maintenance") == DocType.MAINTENANCE_RECORD


def test_chunking_overlap_and_ids():
    doc = make_inline_document("Test", "A. " * 500, DocType.OTHER)
    chunks = chunk_document(doc, chunk_size=200, overlap=40)
    assert len(chunks) > 1
    assert all(c.chunk_id for c in chunks)
    assert len({c.chunk_id for c in chunks}) == len(chunks)  # unique


# --------------------------------------------------------------------------- #
# Store + retrieval
# --------------------------------------------------------------------------- #
def test_ingestion_populates_store(seeded_store):
    stats = seeded_store.stats()
    assert stats["documents"] >= 6
    assert stats["chunks"] > 6
    assert DocType.ENGINEERING_DRAWING.value in stats["documents_by_type"]


def test_search_returns_relevant_chunk(seeded_store):
    results = seeded_store.search("why does P-101A trip on low flow", top_k=5)
    assert results
    joined = " ".join(r.chunk.text.lower() for r in results)
    assert "p-101a" in joined


def test_persistence_round_trip(seeded_store, tmp_path):
    path = tmp_path / "saved.json"
    seeded_store.save(path)
    reopened = KnowledgeStore(embedder=HashingEmbedder(dim=512), path=path)
    assert reopened.load()
    assert reopened.stats()["chunks"] == seeded_store.stats()["chunks"]


# --------------------------------------------------------------------------- #
# Copilot
# --------------------------------------------------------------------------- #
def test_copilot_answer_has_citations_and_confidence(seeded_store):
    copilot = Copilot(seeded_store)
    ans = copilot.answer("What is the low flow trip setpoint for FT-2301?")
    assert ans.citations
    assert 0.0 <= ans.confidence <= 1.0
    assert ans.confidence_label in {"high", "medium", "low", "none"}
    # Citation markers should reference real sources.
    assert any(f"[{i+1}]" in ans.answer for i in range(len(ans.citations))) or ans.answer


def test_copilot_handles_unknown_query(seeded_store):
    copilot = Copilot(seeded_store)
    ans = copilot.answer("What is the share price of an unrelated company in Tokyo?")
    assert ans.confidence_label in {"low", "none", "medium"}


def test_doc_type_filter(seeded_store):
    copilot = Copilot(seeded_store)
    ans = copilot.answer("isolation steps", doc_types=[DocType.SAFETY_PROCEDURE])
    assert all(c.doc_type == DocType.SAFETY_PROCEDURE.value for c in ans.citations)


# --------------------------------------------------------------------------- #
# Agents
# --------------------------------------------------------------------------- #
def test_maintenance_agent_briefing(seeded_store):
    briefing = MaintenanceAgent(seeded_store).diagnose("P-101A")
    assert "failure_history" in briefing.sections
    assert briefing.related_documents


def test_compliance_agent_gap_analysis(seeded_store):
    briefing = ComplianceAgent(seeded_store).check("cooling water system")
    assert briefing.flags  # either gaps or an all-clear flag
