"""No-database mode (DATABASE_URL empty).

- The corpus (corpus/manifest.yaml) is chunked and embedded at startup and kept in memory.
  Embeddings are cached under data/ so restarts are fast.
- Each finished check is saved as data/checks/<id>.json (the same Report the API returns).
"""
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.check.types import ClaimWork
from app.config import settings
from app.corpus_repo import MemoryCorpusRepo
from app.logging import get_logger
from app.schemas import CheckListItem, ClaimOut, Evidence, Report, SourceRef, Summary

log = get_logger(__name__)


class LocalCorpus:
    """Holds the in-memory corpus; `reload()` after the manifest changes."""

    def __init__(self, embedder):
        self._embedder = embedder
        self._lock = threading.Lock()
        self.repo: MemoryCorpusRepo = self._build()

    def _build(self) -> MemoryCorpusRepo:
        from app.ingest.pipeline import build_memory_repo

        repo = build_memory_repo(settings.corpus_path, self._embedder, cache_dir=settings.data_path / "cache")
        log.info("corpus loaded in memory",
                 extra={"kv": {"sources": len(repo.sources()), "chunks": repo.chunk_count()}})
        return repo

    def reload(self) -> MemoryCorpusRepo:
        with self._lock:
            self.repo = self._build()
            return self.repo


def report_from_claims(check_id: str, title: str | None, text: str, claims: list[ClaimWork],
                       summary: dict, created_at: datetime) -> Report:
    out = []
    for c in claims:
        q, s, ch = c.quote, c.source, c.evidence
        out.append(ClaimOut(
            id=str(uuid.uuid4()), ord=c.ord, char_start=c.char_start, char_end=c.char_end, text=c.text,
            claim_type=c.claim_type, citation_raw=c.citation_raw, citation_key=c.citation_key,
            citation_status=c.citation_status, case_name=c.case_name,
            source=SourceRef(id=s.id, title=s.title, citations=list(s.citations or [])) if s else None,
            quote_text=c.quote_text, quote_score=q.score if q else None, quote_match=q.match if q else None,
            quote_diff=q.diff if q else None, quote_critical=q.critical if q else None,
            support_probs=c.support_probs,
            evidence=Evidence(chunk_id=ch.id, source_id=ch.source_id, source_title=ch.source_title,
                              para=ch.para, page_start=ch.page_start, text=ch.text) if ch else None,
            verdict=c.verdict, colour=c.colour, confidence=c.confidence, reason=c.reason, fix=c.fix,
        ))
    return Report(id=check_id, title=title, status="done", input_text=text, summary=Summary(**summary),
                  created_at=created_at, claims=out)


class FileCheckStore:
    def __init__(self, root: Path | None = None):
        self.root = root or settings.data_path / "checks"
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, check_id: str) -> Path:
        return self.root / f"{uuid.UUID(check_id)}.json"   # raises ValueError on a bad id

    def save(self, report: Report) -> None:
        tmp = self._path(report.id).with_suffix(".tmp")
        tmp.write_text(report.model_dump_json(), encoding="utf-8")
        tmp.replace(self._path(report.id))

    def get(self, check_id: str) -> Report | None:
        try:
            p = self._path(check_id)
        except ValueError:
            return None
        return Report.model_validate_json(p.read_text(encoding="utf-8")) if p.exists() else None

    def list(self, limit: int = 20) -> list[CheckListItem]:
        files = sorted(self.root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
        items = []
        for p in files:
            try:
                r = Report.model_validate_json(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            items.append(CheckListItem(id=r.id, title=r.title, status=r.status,
                                       created_at=r.created_at or datetime.now(UTC), summary=r.summary))
        return items
