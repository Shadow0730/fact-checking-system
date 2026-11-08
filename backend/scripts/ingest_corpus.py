"""CLI: ingest every enabled manifest entry. Safe to re-run (unchanged files are skipped).

Without DATABASE_URL there is nothing to ingest into: the app loads the corpus at startup. This script
then just checks every file loads and pre-computes the embedding cache under data/cache/.

    uv run python scripts/ingest_corpus.py [--force] [--only SOURCE_ID ...]
"""
import argparse
import time

import _bootstrap  # noqa: F401

from app.config import settings
from app.ingest.embedder import get_embedder
from app.ingest.manifest import load_manifest
from app.ingest.pipeline import ingest_source
from app.logging import setup_logging


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-ingest even if the file is unchanged")
    ap.add_argument("--only", nargs="*", help="ingest only these source ids")
    args = ap.parse_args()
    setup_logging(settings.log_level)

    corpus = settings.corpus_path
    entries = [e for e in load_manifest(corpus) if e.enabled and (not args.only or e.id in args.only)]
    print(f"Corpus: {corpus}  ({len(entries)} enabled sources)")
    embedder = get_embedder()
    if not settings.use_db:
        from app.ingest.pipeline import build_memory_repo

        repo = build_memory_repo(corpus, embedder, cache_dir=settings.data_path / "cache")
        for s in repo.sources():
            print(f"  {s.id:<32} {repo.chunk_count(s.id):>5} chunks")
        print(f"Done (no database: corpus loads in memory; embeddings cached in {settings.data_path / 'cache'}).")
        return
    from app.db import session_scope

    total, failed = 0, []
    for e in entries:
        t0 = time.perf_counter()
        try:
            with session_scope() as s:
                n, skipped = ingest_source(s, e, corpus, embedder, force=args.force)
        except FileNotFoundError as err:
            print(f"  MISSING  {e.id}: {err}")
            failed.append(e.id)
            continue
        total += n
        status = "skipped (unchanged)" if skipped else f"ingested in {time.perf_counter() - t0:.1f}s"
        print(f"  {e.id:<32} {n:>5} chunks  {status}")
    print(f"Done: {total} chunks across {len(entries) - len(failed)} sources.")
    if failed:
        print(f"Missing files for: {', '.join(failed)}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
