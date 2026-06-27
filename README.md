# Industrial Knowledge Intelligence — Expert Knowledge Copilot

An AI platform that ingests heterogeneous industrial documents — engineering
drawings / P&IDs, maintenance work orders, safety procedures, inspection
reports, operating instructions, project files and regulatory submissions — and
makes their **collective intelligence queryable at the point of need**, on
mobile for field technicians and desktop for engineers.

Every answer is **grounded**: it comes with source citations, a confidence
score, and direct links back to the originating documents.

> Built for the *Industrial Knowledge Intelligence* challenge: knowledge
> fragmentation across 7–12 disconnected document systems, unplanned downtime
> from incomplete equipment context, and the retirement "knowledge cliff".

---

## Why this design

* **Runs fully offline, zero API keys.** The default AI backend uses a
  deterministic hashing embedder + an extractive answer synthesiser, so the
  whole thing demos on a laptop or an air-gapped plant network with no model
  downloads. Drop in OpenAI/Anthropic with one environment variable for
  higher-quality generation.
* **Hybrid retrieval.** Dense cosine similarity is blended with a BM25 lexical
  score, so exact equipment-tag / part-number lookups (`P-101A`, `FT-2301`)
  work as well as semantic questions.
* **Grounded by construction.** Answers carry inline `[n]` citations, a
  calibrated confidence score (semantic agreement × query-term coverage ×
  corroboration), and source links — with explicit low-confidence warnings.
* **Agentic workflows.** Maintenance and compliance agents run multi-pass
  retrieval to assemble briefings (failure history, procedures, inspection
  status, regulatory gaps) that a single query can't.

## Challenge capabilities mapped

| Challenge element | Where it lives |
|---|---|
| RAG over heterogeneous corpora | `iki/rag/copilot.py`, `iki/store/` |
| Knowledge Copilot (citations, confidence, links) | `iki/rag/copilot.py`, `iki/models.py` |
| Mobile-first field UI | `iki/web/index.html` |
| OCR / Document Intelligence (structured + unstructured) | `iki/ingestion/loaders.py` (PDF/CSV/JSON/MD + tag extraction) |
| P&ID / drawing digitisation | `iki/ingestion/loaders.py::load_json_drawing` |
| Industrial ontology (doc types, equipment tags) | `iki/models.py::DocType`, tag regex |
| Agentic maintenance & compliance | `iki/rag/agents.py` |
| Pluggable LLM/embeddings | `iki/ai/` (offline / OpenAI / Anthropic) |

## Quick start

```bash
pip install -r requirements.txt          # core; works offline out of the box

# Option A — one command: seed sample corpus + serve the web app
python run.py
# open http://127.0.0.1:8000 on your laptop or phone

# Option B — CLI
python scripts/seed.py                    # ingest sample_data/
python -m iki.cli ask "Why does pump P-101A keep tripping?"
python -m iki.cli diagnose P-101A         # maintenance briefing (agent)
python -m iki.cli compliance "cooling water system"
python -m iki.cli stats
```

No API key is required for any of the above.

## Using a cloud LLM (optional)

```bash
export IKI_AI_PROVIDER=openai
export OPENAI_API_KEY=sk-...
# or: IKI_AI_PROVIDER=anthropic + ANTHROPIC_API_KEY=...
python -m iki.cli ask "Summarise the failure history of P-101A"
```

If the provider/package/key is missing the system logs a notice and falls back
to the offline backend — it never hard-fails.

## REST API

Run `python run.py` (or `uvicorn iki.api.app:app`), then:

| Method | Path | Purpose |
|---|---|---|
| GET  | `/` | Mobile web chat UI |
| GET  | `/api/health` | Index stats + active embedder |
| POST | `/api/query` | `{ "query": "...", "top_k": 6, "doc_types": [...] }` → answer + citations + confidence |
| GET  | `/api/documents` | List ingested documents |
| GET  | `/api/doc_types` | Available document-type filters |
| POST | `/api/ingest/text` | Ingest raw text |
| POST | `/api/ingest/file` | Upload a file (pdf/csv/json/md/txt) |
| POST | `/api/agent/maintenance` | `{ "equipment": "P-101A" }` → briefing |
| POST | `/api/agent/compliance` | `{ "topic": "cooling water system" }` → gap analysis |

Example:

```bash
curl -s localhost:8000/api/query \
  -H 'content-type: application/json' \
  -d '{"query":"What is the low flow trip setpoint for FT-2301?"}' | python -m json.tool
```

## How it works

```
            ingest                 index                    answer
 documents ───────▶ loaders ─▶ chunker ─▶ embeddings ─▶ KnowledgeStore
 (pdf/csv/json/md)   (type +              (hashing /     (vector + BM25)
                      tag infer)           OpenAI)              │
                                                               ▼
                                   query ─▶ hybrid search ─▶ Copilot ─▶ answer
                                                              (generate +
                                                               cite + score +
                                                               suggest actions)
```

1. **Loaders** detect document type (drawing, maintenance, safety, inspection,
   operating, project, regulatory) from filename + content, extract ISA-style
   equipment tags, and parse structured P&ID JSON sidecars into prose.
2. **Chunker** splits sentence-aware with overlap.
3. **Embeddings** (offline hashing by default) + **BM25** power hybrid search.
4. **Copilot** generates a grounded answer, attaches citations + confidence,
   and surfaces next-best actions (raise work order, confirm permit, etc.).

## Document formats supported

* `.json` — structured P&ID / drawing digitisation (equipment, lines, instruments)
* `.csv` — CMMS / work-order exports (flattened to records)
* `.md` / `.txt` — procedures, instructions, reports (optional `--- front-matter ---`)
* `.pdf` — text extraction via `pypdf`; scanned PDFs are flagged for OCR

Add a document type explicitly with front-matter:

```
---
title: SOP — Lockout/Tagout for Cooling Water Pumps
doc_type: safety_procedure
---
```

## Sample corpus

`sample_data/` models a cooling-water system (pumps P-101A/B, exchanger HX-12,
surge vessel V-201) across all seven document types — including a retiring
engineer's *tribal-knowledge* handover note, so you can see the "knowledge
cliff" problem being solved: ask *"why does P-101A keep tripping?"* and the
Copilot surfaces the undocumented "check the surge-vessel level first" insight
with a citation.

## Tests

```bash
pip install pytest
pytest -q          # 13 tests: embeddings, loaders, chunking, store,
                   # persistence, copilot citations/confidence, agents
```

## Project layout

```
iki/
  ingestion/   loaders, chunker, pipeline
  ai/          embeddings + generation (offline | openai | anthropic)
  store/       persistent hybrid vector+lexical store
  rag/         copilot + maintenance/compliance agents
  api/         FastAPI app
  web/         mobile-first chat UI
sample_data/   demo industrial corpus (7 doc types)
scripts/seed.py
tests/
```

## Notes & extensibility

* Swap the JSON store for pgvector / a real vector DB by reimplementing
  `KnowledgeStore` — the interface is small.
* The structured P&ID loader is the seam for a computer-vision drawing-parsing
  pipeline: emit the same JSON shape and the rest works unchanged.
* `_ACTION_RULES` in `copilot.py` is where agentic CMMS/QMS integrations hook in.

