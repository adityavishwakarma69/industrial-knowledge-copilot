"""Command-line interface for the Industrial Knowledge Copilot.

Examples
--------
    python -m iki.cli ingest sample_data
    python -m iki.cli ask "Why does pump P-101A keep tripping?"
    python -m iki.cli diagnose P-101A
    python -m iki.cli stats
    python -m iki.cli serve
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import settings
from .ingestion import IngestionPipeline
from .models import DocType
from .rag import Copilot, MaintenanceAgent, ComplianceAgent
from .store import KnowledgeStore


def _store() -> KnowledgeStore:
    settings.ensure_dirs()
    return KnowledgeStore.open()


def cmd_ingest(args) -> None:
    store = _store()
    pipeline = IngestionPipeline(store)
    from pathlib import Path
    p = Path(args.path)
    result = pipeline.ingest_directory(p) if p.is_dir() else pipeline.ingest_file(p)
    store.save()
    print(json.dumps(result.to_dict(), indent=2))
    print(f"\nIndex saved to {store.path} | {store.stats()['chunks']} chunks total")


def cmd_ask(args) -> None:
    store = _store()
    copilot = Copilot(store)
    dtypes = [DocType(t) for t in args.type] if args.type else None
    ans = copilot.answer(args.query, top_k=args.top_k, doc_types=dtypes)
    if args.json:
        print(json.dumps(ans.to_dict(), indent=2))
        return
    print(f"\nQ: {ans.query}\n")
    print(ans.answer)
    print(f"\nConfidence: {ans.confidence_label.upper()} ({ans.confidence:.0%}) · provider: {ans.provider}")
    if ans.suggested_actions:
        print("\nSuggested actions:")
        for a in ans.suggested_actions:
            print(f"  ▸ {a}")
    if ans.citations:
        print("\nSources:")
        for i, c in enumerate(ans.citations, 1):
            print(f"  [{i}] {c.title}  ({c.doc_type}, match {c.score:.0%})")
            print(f"      {c.source_path}")
    for w in ans.warnings:
        print(f"  ⚠ {w}")


def cmd_diagnose(args) -> None:
    store = _store()
    briefing = MaintenanceAgent(store).diagnose(args.equipment)
    print(json.dumps(briefing.to_dict(), indent=2) if args.json else _fmt_briefing(briefing))

def cmd_equipment(args) -> None:
    store = _store()
    copilot = Copilot(store)
    info = copilot.equipment_brief(args.tag)
    print(json.dumps(info, indent=2))


def cmd_compliance(args) -> None:
    store = _store()
    briefing = ComplianceAgent(store).check(args.topic)
    print(json.dumps(briefing.to_dict(), indent=2) if args.json else _fmt_briefing(briefing))


def _fmt_briefing(b) -> str:
    out = [f"\n=== {b.subject} ==="]
    for name, ans in b.sections.items():
        out.append(f"\n## {name.replace('_',' ').title()}  [{ans.confidence_label}]")
        out.append(ans.answer)
    if b.flags:
        out.append("\nFlags:")
        out.extend(f"  • {f}" for f in b.flags)
    if b.related_documents:
        out.append("\nRelated documents:")
        out.extend(f"  - {d['title']} ({d['doc_type']})" for d in b.related_documents)
    return "\n".join(out)


def cmd_stats(args) -> None:
    store = _store()
    print(json.dumps(store.stats(), indent=2))


def cmd_serve(args) -> None:
    import uvicorn
    uvicorn.run("iki.api.app:app", host=args.host, port=args.port, reload=args.reload)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="iki", description="Industrial Knowledge Copilot CLI")
    sub = p.add_subparsers(dest="command", required=True)

    pi = sub.add_parser("ingest", help="Ingest a file or directory")
    pi.add_argument("path")
    pi.set_defaults(func=cmd_ingest)

    pa = sub.add_parser("ask", help="Ask the Copilot a question")
    pa.add_argument("query")
    pa.add_argument("--top-k", type=int, default=None)
    pa.add_argument("--type", action="append", help="Filter by doc_type (repeatable)")
    pa.add_argument("--json", action="store_true")
    pa.set_defaults(func=cmd_ask)

    pd = sub.add_parser("diagnose", help="Maintenance briefing for equipment")
    pd.add_argument("equipment")
    pd.add_argument("--json", action="store_true")
    pd.set_defaults(func=cmd_diagnose)

    pe = sub.add_parser("equipment", help="Show everything linked to an equipment tag")
    pe.add_argument("tag")
    pe.set_defaults(func=cmd_equipment)

    pc = sub.add_parser("compliance", help="Compliance gap check for a topic")
    pc.add_argument("topic")
    pc.add_argument("--json", action="store_true")
    pc.set_defaults(func=cmd_compliance)

    ps = sub.add_parser("stats", help="Show index statistics")
    ps.set_defaults(func=cmd_stats)

    pv = sub.add_parser("serve", help="Run the web app + API")
    pv.add_argument("--host", default="127.0.0.1")
    pv.add_argument("--port", type=int, default=8000)
    pv.add_argument("--reload", action="store_true")
    pv.set_defaults(func=cmd_serve)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
