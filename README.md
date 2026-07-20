# Industrial Knowledge Copilot

A retrieval-augmented system that unifies scattered industrial documentation — P&IDs, maintenance work orders, safety procedures, inspection reports, operating instructions, project files, and regulatory submissions — into a single, queryable knowledge base. Answers are grounded: every response includes source citations, a confidence score, and links back to the originating documents.

Built for field technicians (mobile) and engineers (desktop) who need an answer at the point of need, not a folder search across seven disconnected systems.

## Table of Contents

- [Problem](#problem)
- [Why This Design](#why-this-design)
- [How It Works](#how-it-works)
- [Quick Start](#quick-start)
- [Using a Cloud LLM](#using-a-cloud-llm-optional)
- [REST API](#rest-api)
- [Supported Document Formats](#supported-document-formats)
- [Sample Corpus](#sample-corpus)
- [Tests](#tests)
- [Project Structure](#project-structure)
- [Extending the System](#extending-the-system)
- [Contributing](#contributing)
- [License](#license)

## Problem

Industrial sites accumulate knowledge across many disconnected systems — CMMS, document management, drawing archives, compliance logs — with no single point of query. Two consequences follow directly:

- **Unplanned downtime** from incomplete equipment context at the moment a decision is needed.
- **The retirement knowledge cliff** — undocumented, experience-based insight leaving with the people who hold it.

This project addresses both by indexing the existing document corpus as-is and answering natural-language questions against it, with enough traceability that an engineer can verify the answer rather than just trust it.

## Why This Design

- **Runs fully offline, no API keys required.** The default backend uses a deterministic hashing embedder and an extractive answer synthesizer, so the system runs on a laptop or an air-gapped plant network without downloading a model. An OpenAI or Anthropic backend can be enabled with one environment variable for higher-quality generation.
- **Hybrid retrieval.** Dense cosine similarity is combined with BM25 lexical scoring, so exact equipment-tag or part-number lookups (`P-101A`, `FT-2301`) work alongside semantic questions.
- **Grounded by construction.** Every answer carries inline `[n]` citations, a calibrated confidence score (semantic agreement × query-term coverage × corroboration), and source links, with explicit low-confidence warnings when evidence is thin.
- **Agentic workflows.** Maintenance and compliance agents run multi-pass retrieval to assemble briefings — failure history, applicable procedures, inspection status, regulatory gaps — that a single query cannot.

## How It Works

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

1. **Loaders** detect document type (drawing, maintenance, safety, inspection, operating, project, regulatory) from filename and content, extract ISA-style equipment tags, and parse structured P&ID JSON sidecars into prose.
2. **Chunker** splits text sentence-aware, with overlap, to preserve context across chunk boundaries.
3. **Embeddings** (offline hashing by default, or OpenAI/Anthropic if configured) combine with **BM25** to power hybrid search.
4. **Copilot** generates a grounded answer, attaches citations and a confidence score, and surfaces next-best actions such as raising a work order or confirming a permit.

## Quick Start

```bash
pip install -r requirements.txt          # core dependencies; works offline out of the box

# Option A — one command: seed the sample corpus and serve the web app
python run.py
# open http://127.0.0.1:8000 on a laptop or phone

# Option B — CLI
python scripts/seed.py                    # ingest sample_data/
python -m iki.cli ask "what should I check first when P-101A trips"
python -m iki.cli diagnose P-101A         # maintenance briefing (agent)
python -m iki.cli compliance "cooling water system"
python -m iki.cli stats
```

No API key is required for any of the above.

## Using a Cloud LLM (optional)

```bash
export IKI_AI_PROVIDER=openai
export OPENAI_API_KEY=sk-...
# or: IKI_AI_PROVIDER=anthropic, with ANTHROPIC_API_KEY=...

python -m iki.cli ask "Summarise the failure history of P-101A"
```

If the configured provider, package, or key is missing, the system logs a notice and falls back to the offline backend. It does not hard-fail.

## REST API

Start the server with `python run.py` (or `uvicorn iki.api.app:app`).

| Method | Path                     | Purpose                                                                                 |
|--------|--------------------------|------------------------------------------------------------------------------------------|
| GET    | `/`                      | Mobile-first web chat UI                                                                 |
| GET    | `/api/health`            | Index stats and active embedder                                                          |
| POST   | `/api/query`             | `{ "query": "...", "top_k": 6, "doc_types": [...] }` → answer, citations, confidence      |
| GET    | `/api/documents`         | List ingested documents                                                                   |
| GET    | `/api/doc_types`         | Available document-type filters                                                          |
| POST   | `/api/ingest/text`       | Ingest raw text                                                                           |
| POST   | `/api/ingest/file`       | Upload a file (pdf/csv/json/md/txt)                                                       |
| POST   | `/api/agent/maintenance` | `{ "equipment": "P-101A" }` → maintenance briefing                                        |
| POST   | `/api/agent/compliance`  | `{ "topic": "cooling water system" }` → compliance gap analysis                           |

Example query:

```bash
curl -s localhost:8000/api/query \
  -H 'content-type: application/json' \
  -d '{"query":"What is the low flow trip setpoint for FT-2301?"}' | python -m json.tool
```

## Supported Document Formats

- `.json` — structured P&ID / drawing digitization (equipment, lines, instruments)
- `.csv` — CMMS / work-order exports, flattened to records
- `.md` / `.txt` — procedures, instructions, reports (optional front-matter)
- `.pdf` — text extraction via `pypdf`; scanned PDFs are flagged for OCR

A document type can be set explicitly with front-matter:

```markdown
---
title: SOP — Lockout/Tagout for Cooling Water Pumps
doc_type: safety_procedure
---
```

## Sample Corpus

`sample_data/` models a cooling-water system (pumps P-101A/B, exchanger HX-12, surge vessel V-201) across all seven document types, including a retiring engineer's tribal-knowledge handover note. Asking *"why does P-101A keep tripping?"* surfaces the undocumented "check the surge-vessel level first" insight, with a citation back to that note — a concrete example of the knowledge-cliff problem this project targets.

## Tests

```bash
pip install pytest
pytest -q
```

13 tests cover embeddings, loaders, chunking, the store, persistence, copilot citations/confidence, and the agents.

## Project Structure

```
iki/
  ingestion/   loaders, chunker, pipeline
  ai/          embeddings and generation (offline | openai | anthropic)
  store/       persistent hybrid vector + lexical store
  rag/         copilot and maintenance/compliance agents
  api/         FastAPI app
  web/         mobile-first chat UI
sample_data/   demo industrial corpus (7 document types)
scripts/seed.py
tests/
```

## Extending the System

- Swap the JSON store for pgvector or another vector database by reimplementing `KnowledgeStore` — the interface is small.
- The structured P&ID loader is the seam for a computer-vision drawing-parsing pipeline: emit the same JSON shape and the rest of the pipeline works unchanged.
- `_ACTION_RULES` in `copilot.py` is where CMMS/QMS integrations for agentic actions hook in.

## Contributing

Issues and pull requests are welcome. Before opening a PR:

1. Run `pytest -q` and make sure the existing suite passes.
2. Add tests for new loaders, retrieval logic, or agent behavior.
3. Keep offline-mode compatibility intact — no change should require an API key to run the core demo.

A formal `CONTRIBUTING.md` and contributor guidelines are not yet in place; open an issue first for anything beyond a small fix so the approach can be agreed on before implementation.

## License

No license file is currently included in this repository. Until one is added, all rights are reserved by default and reuse should not be assumed. If you intend to open this project up for external contributions or reuse, see [choosealicense.com](https://choosealicense.com/) for guidance on picking one.
