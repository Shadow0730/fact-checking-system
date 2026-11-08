import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import ValidationError
from sqlalchemy import func, select

from app.config import settings
from app.db import get_session
from app.errors import AppError
from app.ingest.embedder import get_embedder
from app.ingest.loaders import SUPPORTED
from app.ingest.manifest import ManifestEntry, append_entry, load_manifest
from app.ingest.pipeline import ingest_source
from app.models import Chunk, Source
from app.schemas import IngestResult, SourceMeta, SourceOut

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("", response_model=list[SourceOut])
def list_sources(request: Request, session=Depends(get_session)) -> list[SourceOut]:
    if session is None:
        repo = request.app.state.corpus.repo
        lang = {e.id: e.language for e in load_manifest(settings.corpus_path)}
        rows = sorted(repo.sources(), key=lambda s: (s.doc_type, -(s.year or 0), s.title))
        return [SourceOut(id=s.id, title=s.title, doc_type=s.doc_type, court=s.court, year=s.year,
                          language=lang.get(s.id, "en"), citations=list(s.citations),
                          citation_keys=list(s.citation_keys), chunks=repo.chunk_count(s.id)) for s in rows]
    counts = dict(session.execute(select(Chunk.source_id, func.count()).group_by(Chunk.source_id)).all())
    rows = session.execute(select(Source).order_by(Source.doc_type, Source.year.desc().nulls_last(), Source.title)).scalars()
    return [SourceOut(id=s.id, title=s.title, doc_type=s.doc_type, court=s.court, year=s.year, language=s.language,
                      citations=list(s.citations or []), citation_keys=list(s.citation_keys or []),
                      chunks=counts.get(s.id, 0)) for s in rows]


@router.post("", response_model=IngestResult)
async def upload_source(request: Request, file: UploadFile = File(...), meta: str = Form(...),
                        session=Depends(get_session)):
    try:
        m = SourceMeta.model_validate(json.loads(meta))
    except (json.JSONDecodeError, ValidationError) as e:
        raise AppError("INVALID_REQUEST", 422, f"Invalid meta: {e}") from e
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED:
        raise AppError("UNSUPPORTED_FILE", 415, f"Unsupported file type {suffix!r}; use .pdf, .docx or .txt")
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise AppError("FILE_TOO_LARGE", 413, f"File is larger than {settings.max_upload_mb} MB")

    corpus = settings.corpus_path
    rel = f"files/uploads/{m.id}{suffix}"
    (corpus / rel).parent.mkdir(parents=True, exist_ok=True)
    (corpus / rel).write_bytes(data)
    entry = ManifestEntry(**m.model_dump(), file=rel, enabled=True)
    append_entry(corpus, entry)
    if session is None:
        repo = request.app.state.corpus.reload()
        return IngestResult(id=m.id, chunks=repo.chunk_count(m.id), skipped=False)
    n, skipped = ingest_source(session, entry, corpus, get_embedder(), force=True)
    return IngestResult(id=m.id, chunks=n, skipped=skipped)
