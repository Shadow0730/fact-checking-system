"""FastAPI app: CORS, routers, startup (embedding model loaded once, one shared httpx client)."""
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import errors
from app.clients import make_clients
from app.config import settings
from app.ingest.embedder import get_embedder
from app.logging import get_logger, setup_logging
from app.routers import checks, eval, health, sources

setup_logging(settings.log_level)
log = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.offline_mode:
        log.warning("OFFLINE_MODE=true: claim extraction and judging are heuristics; results are NOT meaningful")
    embedder = get_embedder()  # load once, up front, rather than on the first request
    app.state.corpus = app.state.store = None
    if not settings.use_db:
        from app.local_store import FileCheckStore, LocalCorpus

        log.info("DATABASE_URL not set: corpus in memory, checks saved under data/checks/")
        app.state.corpus = LocalCorpus(embedder)
        app.state.store = FileCheckStore()
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=settings.sarvam_max_concurrency * 2)) as http:
        app.state.llm, app.state.prism = make_clients(http)
        app.state.online = None
        if settings.indiankanoon_api_token:
            from app.clients.indiankanoon import IndianKanoon

            app.state.online = IndianKanoon(http)
            log.info("Indian Kanoon lookups ON for citations not in the local corpus")
        yield


app = FastAPI(title="Legal Fact Checker", version="0.1.0", lifespan=lifespan)
errors.install(app)
# Added last = outermost, so every response (errors included) carries the CORS headers.
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_methods=["*"], allow_headers=["*"])
app.include_router(health.router)
app.include_router(sources.router)
app.include_router(checks.router)
app.include_router(eval.router)
