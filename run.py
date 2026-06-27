#!/usr/bin/env python3
"""Convenience launcher: seed the sample corpus (if empty) and serve the app.

    python run.py            # seed if needed, then start the web app
    python run.py --no-seed  # just serve
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from iki.config import settings
from iki.ingestion import IngestionPipeline
from iki.store import KnowledgeStore


def main() -> None:
    settings.ensure_dirs()
    store = KnowledgeStore.open()
    if "--no-seed" not in sys.argv and store.stats()["chunks"] == 0:
        print("Empty index — seeding from sample_data/ ...")
        IngestionPipeline(store).ingest_directory(Path(__file__).resolve().parent / "sample_data")
        store.save()
        print(f"Seeded {store.stats()['chunks']} chunks.")
    import uvicorn
    print("Serving on http://127.0.0.1:8000  (open in a browser / phone)")
    uvicorn.run("iki.api.app:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
