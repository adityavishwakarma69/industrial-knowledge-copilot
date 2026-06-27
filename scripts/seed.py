"""Seed the knowledge store from the bundled sample corpus.

Usage:
    python scripts/seed.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from iki.config import settings           # noqa: E402
from iki.ingestion import IngestionPipeline  # noqa: E402
from iki.store import KnowledgeStore      # noqa: E402


def main() -> None:
    settings.ensure_dirs()
    store = KnowledgeStore.open()
    store.clear()  # fresh build for a clean demo
    pipeline = IngestionPipeline(store)
    result = pipeline.ingest_directory(ROOT / "sample_data")
    store.save()

    print("Ingested sample corpus:")
    print(f"  documents : {result.documents}")
    print(f"  chunks    : {result.chunks}")
    if result.skipped:
        print(f"  skipped   : {result.skipped}")
    if result.warnings:
        print(f"  warnings  : {result.warnings}")
    print(f"\nIndex saved to: {store.path}")
    print("\nStore stats:")
    for k, v in store.stats().items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
