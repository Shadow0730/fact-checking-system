from fastapi import APIRouter, Request
from sqlalchemy import func, select

from app.config import settings
from app.db import db_ok, session_scope
from app.ingest.embedder import is_loaded
from app.models import Chunk, Source
from app.schemas import Health

router = APIRouter()


@router.get("/health", response_model=Health)
def health(request: Request) -> Health:
    if not settings.use_db:
        corpus = getattr(request.app.state, "corpus", None)
        repo = corpus.repo if corpus else None
        return Health(db="memory", embedding_model=settings.embedding_model, embedding_loaded=is_loaded(),
                      sources=len(repo.sources()) if repo else 0, chunks=repo.chunk_count() if repo else 0,
                      offline_mode=settings.offline_mode, online_lookup=bool(settings.indiankanoon_api_token))
    ok = db_ok()
    n_sources = n_chunks = 0
    if ok:
        with session_scope() as s:
            n_sources = s.execute(select(func.count()).select_from(Source)).scalar_one()
            n_chunks = s.execute(select(func.count()).select_from(Chunk)).scalar_one()
    return Health(db="ok" if ok else "unreachable", embedding_model=settings.embedding_model,
                  embedding_loaded=is_loaded(), sources=n_sources, chunks=n_chunks,
                  offline_mode=settings.offline_mode, online_lookup=bool(settings.indiankanoon_api_token))
