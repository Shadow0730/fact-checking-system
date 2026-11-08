"""ingest_source(entry): load -> chunk -> embed -> insert. Idempotent (skips unchanged files)."""
import hashlib
import os
import threading
import time
from pathlib import Path

import numpy as np

from app.check.citations import citation_key
from app.check.types import ChunkInfo, SourceInfo
from app.config import settings
from app.corpus_repo import MemoryCorpusRepo
from app.ingest.chunker import RawChunk, chunk_document
from app.ingest.loaders import load_file
from app.ingest.manifest import ManifestEntry, load_manifest
from app.logging import get_logger

log = get_logger(__name__)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def citation_keys_for(entry: ManifestEntry) -> list[str]:
    keys = [citation_key(c) for c in entry.citations]
    return sorted({k for k in keys if k})


def chunk_entry(entry: ManifestEntry, corpus_dir: Path) -> list[RawChunk]:
    path = corpus_dir / entry.file
    if not path.exists():
        raise FileNotFoundError(f"{entry.id}: file not found: {path}")
    return chunk_document(load_file(path), entry.effective_sectioning,
                          settings.chunk_target_chars, settings.chunk_max_chars)


def source_info(entry: ManifestEntry) -> SourceInfo:
    return SourceInfo(entry.id, entry.title, entry.doc_type, entry.court, entry.year,
                      list(entry.citations), citation_keys_for(entry), [a.lower() for a in entry.aliases])


def ingest_source(session, entry: ManifestEntry, corpus_dir: Path, embedder, force: bool = False) -> tuple[int, bool]:
    """Returns (number of chunks, skipped)."""
    from sqlalchemy import delete, func, select

    from app.models import Chunk, Source

    path = corpus_dir / entry.file
    digest = sha256_of(path)
    existing = session.get(Source, entry.id)
    if existing and existing.sha256 == digest and not force:
        n = session.execute(select(func.count()).select_from(Chunk).where(Chunk.source_id == entry.id)).scalar_one()
        return n, True

    raw = chunk_entry(entry, corpus_dir)
    vecs = embedder.embed([c.text for c in raw])
    info = source_info(entry)
    if existing is None:
        existing = Source(id=entry.id)
        session.add(existing)
    existing.title, existing.doc_type, existing.court, existing.year = entry.title, entry.doc_type, entry.court, entry.year
    existing.language, existing.citations, existing.citation_keys = entry.language, info.citations, info.citation_keys
    existing.aliases, existing.file_path, existing.sha256 = info.aliases, entry.file, digest
    session.flush()
    session.execute(delete(Chunk).where(Chunk.source_id == entry.id))
    session.add_all([
        Chunk(source_id=entry.id, ord=c.ord, page_start=c.page_start, page_end=c.page_end,
              para=c.para, text=c.text, embedding=v.tolist())
        for c, v in zip(raw, vecs)
    ])
    session.commit()
    log.info("ingested", extra={"kv": {"source": entry.id, "chunks": len(raw)}})
    return len(raw), False


def cached_embed(embedder, texts: list[str], cache_dir: Path | None) -> np.ndarray:
    """Embed texts, reusing a per-text cache on disk (so restarts and new sources only embed what's new)."""
    if cache_dir is None or not texts:
        return np.asarray(embedder.embed(texts))
    tag = hashlib.sha256(f"{settings.embedding_model}|{settings.embedding_dim}".encode()).hexdigest()[:12]
    path = cache_dir / f"embeddings-{tag}.npz"
    with _CACHE_LOCK:
        known: dict[str, np.ndarray] = {}
        if path.exists():
            try:
                # The context manager closes the file: on Windows an open .npz cannot be replaced.
                with np.load(path) as z:
                    known = dict(zip(z["keys"].tolist(), np.array(z["vecs"])))
            except Exception:
                known = {}
        keys = [hashlib.sha1(t.encode("utf-8")).hexdigest() for t in texts]
        missing = [i for i, k in enumerate(keys) if k not in known]
        if missing:
            vecs = np.asarray(embedder.embed([texts[i] for i in missing]), dtype=np.float32)
            for i, v in zip(missing, vecs):
                known[keys[i]] = v
            _write_cache(path, known)
        return np.stack([known[k] for k in keys])


_CACHE_LOCK = threading.Lock()


def _write_cache(path: Path, known: dict[str, np.ndarray]) -> None:
    """Best effort: a failed cache write must never fail a check (it only costs a re-embed later)."""
    tmp = path.with_name(f"{path.stem}.{os.getpid()}.{threading.get_ident()}.tmp.npz")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(tmp, keys=np.array(list(known.keys())), vecs=np.stack(list(known.values())))
        for attempt in range(5):     # Windows: antivirus / indexer can hold the file for a moment
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                time.sleep(0.1 * (attempt + 1))
        log.warning("embedding cache not saved (file in use)", extra={"kv": {"path": str(path)}})
    except Exception as e:
        log.warning("embedding cache not saved", extra={"kv": {"err": str(e)[:200]}})
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def build_memory_repo(corpus_dir: Path, embedder=None, only_enabled: bool = True,
                      cache_dir: Path | None = None) -> MemoryCorpusRepo:
    """The whole corpus in memory: used by the app when there is no database, by tests,
    the eval-set builder, and DB-free evaluation."""
    sources, chunks = [], []
    for entry in load_manifest(corpus_dir):
        if only_enabled and not entry.enabled:
            continue
        if not (corpus_dir / entry.file).exists():
            log.warning("missing corpus file, skipped", extra={"kv": {"source": entry.id, "file": entry.file}})
            continue
        sources.append(source_info(entry))
        for rc in chunk_entry(entry, corpus_dir):
            chunks.append(ChunkInfo(len(chunks) + 1, entry.id, entry.title, rc.ord, rc.text,
                                    rc.para, rc.page_start, rc.page_end))
    emb = cached_embed(embedder, [c.text for c in chunks], cache_dir) if (embedder is not None and chunks) else None
    return MemoryCorpusRepo(sources, chunks, emb)
