"""Read access to the source corpus.

`SqlCorpusRepo` is the real one (Postgres + pgvector). `MemoryCorpusRepo` holds the same data
in Python lists; it backs the offline tests and the eval-set builder, so the check steps
(resolver, retriever, quotes) can be exercised without a database.
"""
import re
from collections.abc import Sequence
from typing import Protocol

import numpy as np

from app.check.normalize import norm_name
from app.check.types import ChunkInfo, SourceInfo

_STOP = set("""a an the of to in on at by for from with and or but is are was were be been being as that this
these those it its which who whom whose such any all no not under shall may must has have had do does did
there their than then so if into upon also said same court held hold holds""".split())
_TOKEN = re.compile(r"[a-z0-9]+")


def content_terms(text: str, limit: int = 24) -> list[str]:
    seen: list[str] = []
    for w in _TOKEN.findall(text.lower()):
        if (w not in _STOP and len(w) > 2 or w.isdigit()) and w not in seen:
            seen.append(w)
    return seen[:limit]


class CorpusRepo(Protocol):
    def get_source(self, source_id: str) -> SourceInfo | None: ...
    def find_source_by_key(self, key: str) -> SourceInfo | None: ...
    def sources(self, doc_types: Sequence[str] | None = None) -> list[SourceInfo]: ...
    def alias_index(self) -> list[tuple[str, str]]: ...
    def chunks_of(self, source_id: str) -> list[ChunkInfo]: ...
    def chunks_by_para(self, source_id: str, para: str) -> list[ChunkInfo]: ...
    def get_chunks(self, ids: Sequence[int]) -> list[ChunkInfo]: ...
    def vector_search(self, vec: np.ndarray, source_id: str | None, n: int,
                      exclude_source: str | None = None) -> list[int]: ...
    def keyword_search(self, query: str, source_id: str | None, n: int,
                       exclude_source: str | None = None) -> list[int]: ...


def _alias_rows(sources: Sequence[SourceInfo]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for s in sources:
        for name in [s.title, *s.aliases]:
            n = norm_name(name)
            if n:
                rows.append((n, s.id))
    return rows


# ── In-memory ────────────────────────────────────────────────────────────────
class MemoryCorpusRepo:
    def __init__(self, sources: Sequence[SourceInfo], chunks: Sequence[ChunkInfo],
                 embeddings: np.ndarray | None = None):
        self._sources = {s.id: s for s in sources}
        self._chunks = list(chunks)
        self._by_id = {c.id: c for c in self._chunks}
        self._emb = embeddings

    def get_source(self, source_id):
        return self._sources.get(source_id)

    def chunk_count(self, source_id: str | None = None) -> int:
        return sum(1 for c in self._chunks if source_id is None or c.source_id == source_id)

    def find_source_by_key(self, key):
        return next((s for s in self._sources.values() if key in s.citation_keys), None)

    def sources(self, doc_types=None):
        return [s for s in self._sources.values() if doc_types is None or s.doc_type in doc_types]

    def alias_index(self):
        return _alias_rows(list(self._sources.values()))

    def chunks_of(self, source_id):
        return sorted((c for c in self._chunks if c.source_id == source_id), key=lambda c: c.ord)

    def chunks_by_para(self, source_id, para):
        return [c for c in self.chunks_of(source_id) if (c.para or "").upper() == para.upper()]

    def get_chunks(self, ids):
        return [self._by_id[i] for i in ids if i in self._by_id]

    def add_entry(self, entry, corpus_dir, embedder) -> int:
        """Add (or replace) one manifest source at runtime. Returns its chunk count."""
        from app.config import settings
        from app.ingest.pipeline import cached_embed, chunk_entry, source_info

        raw = chunk_entry(entry, corpus_dir)
        next_id = max((c.id for c in self._chunks), default=0) + 1
        new = [ChunkInfo(next_id + i, entry.id, entry.title, rc.ord, rc.text, rc.para, rc.page_start, rc.page_end)
               for i, rc in enumerate(raw)]
        keep = [i for i, c in enumerate(self._chunks) if c.source_id != entry.id]
        new_emb = None
        if embedder is not None and new:
            new_emb = cached_embed(embedder, [c.text for c in new], settings.data_path / "cache")
        if self._emb is not None and new_emb is not None:
            self._emb = np.vstack([self._emb[keep], new_emb]) if keep else np.asarray(new_emb)
        elif new_emb is not None and not self._chunks:
            self._emb = np.asarray(new_emb)
        self._chunks = [self._chunks[i] for i in keep] + new
        self._by_id = {c.id: c for c in self._chunks}
        self._sources[entry.id] = source_info(entry)
        return len(new)

    def _pool(self, source_id, exclude_source):
        return [i for i, c in enumerate(self._chunks)
                if (source_id is None or c.source_id == source_id)
                and (exclude_source is None or c.source_id != exclude_source)]

    def vector_search(self, vec, source_id, n, exclude_source=None):
        if self._emb is None:
            return []
        pool = self._pool(source_id, exclude_source)
        if not pool:
            return []
        sims = self._emb[pool] @ np.asarray(vec)
        order = np.argsort(-sims)[:n]
        return [self._chunks[pool[i]].id for i in order]

    def keyword_search(self, query, source_id, n, exclude_source=None):
        terms = set(content_terms(query))
        if not terms:
            return []
        scored = []
        for i in self._pool(source_id, exclude_source):
            words = set(_TOKEN.findall(self._chunks[i].text.lower()))
            hits = len(terms & words)
            if hits:
                scored.append((hits, self._chunks[i].id))
        scored.sort(key=lambda x: -x[0])
        return [cid for _, cid in scored[:n]]


# ── Postgres ─────────────────────────────────────────────────────────────────
class SqlCorpusRepo:
    def __init__(self, session):
        from sqlalchemy import select, text

        from app.models import Chunk, Source

        self.s = session
        self._select, self._text, self.Chunk, self.Source = select, text, Chunk, Source
        self._titles: dict[str, str] | None = None

    def _src(self, row) -> SourceInfo:
        return SourceInfo(row.id, row.title, row.doc_type, row.court, row.year,
                          list(row.citations or []), list(row.citation_keys or []), list(row.aliases or []))

    def add_entry(self, entry, corpus_dir, embedder) -> int:
        from app.ingest.pipeline import ingest_source

        n, _ = ingest_source(self.s, entry, corpus_dir, embedder, force=True)
        self._titles = None
        return n

    def _title(self, source_id: str) -> str:
        if self._titles is None:
            self._titles = dict(self.s.execute(self._select(self.Source.id, self.Source.title)).all())
        return self._titles.get(source_id, source_id)

    def _chunk(self, row) -> ChunkInfo:
        return ChunkInfo(row.id, row.source_id, self._title(row.source_id), row.ord, row.text,
                         row.para, row.page_start, row.page_end)

    def get_source(self, source_id):
        row = self.s.get(self.Source, source_id)
        return self._src(row) if row else None

    def find_source_by_key(self, key):
        row = self.s.execute(
            self._select(self.Source).where(self.Source.citation_keys.contains([key]))
        ).scalars().first()
        return self._src(row) if row else None

    def sources(self, doc_types=None):
        q = self._select(self.Source)
        if doc_types:
            q = q.where(self.Source.doc_type.in_(list(doc_types)))
        return [self._src(r) for r in self.s.execute(q).scalars()]

    def alias_index(self):
        return _alias_rows(self.sources())

    def chunks_of(self, source_id):
        q = self._select(self.Chunk).where(self.Chunk.source_id == source_id).order_by(self.Chunk.ord)
        return [self._chunk(r) for r in self.s.execute(q).scalars()]

    def chunks_by_para(self, source_id, para):
        from sqlalchemy import func

        q = (self._select(self.Chunk)
             .where(self.Chunk.source_id == source_id, func.upper(self.Chunk.para) == para.upper())
             .order_by(self.Chunk.ord))
        return [self._chunk(r) for r in self.s.execute(q).scalars()]

    def get_chunks(self, ids):
        if not ids:
            return []
        rows = {r.id: r for r in self.s.execute(
            self._select(self.Chunk).where(self.Chunk.id.in_(list(ids)))).scalars()}
        return [self._chunk(rows[i]) for i in ids if i in rows]

    def vector_search(self, vec, source_id, n, exclude_source=None):
        q = self._select(self.Chunk.id)
        if source_id:
            q = q.where(self.Chunk.source_id == source_id)
        if exclude_source:
            q = q.where(self.Chunk.source_id != exclude_source)
        q = q.order_by(self.Chunk.embedding.cosine_distance(list(map(float, vec)))).limit(n)
        return list(self.s.execute(q).scalars())

    def keyword_search(self, query, source_id, n, exclude_source=None):
        terms = content_terms(query)
        if not terms:
            return []
        tsq = " or ".join(terms)
        where = ["tsv @@ websearch_to_tsquery('english', :q)"]
        params: dict = {"q": tsq, "n": n}
        if source_id:
            where.append("source_id = :sid")
            params["sid"] = source_id
        if exclude_source:
            where.append("source_id <> :ex")
            params["ex"] = exclude_source
        sql = (f"SELECT id FROM chunks WHERE {' AND '.join(where)} "
               "ORDER BY ts_rank(tsv, websearch_to_tsquery('english', :q)) DESC LIMIT :n")
        return [r[0] for r in self.s.execute(self._text(sql), params)]
