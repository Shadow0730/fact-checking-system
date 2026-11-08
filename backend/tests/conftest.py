import os
import sys
from pathlib import Path

# Tests never need a key or a model download.
os.environ.setdefault("OFFLINE_MODE", "true")
os.environ.setdefault("EMBEDDING_MODEL", "hash")
os.environ.setdefault("EMBEDDING_DIM", "1024")
# No database by default (in-memory mode). Export DATABASE_URL to also run the tests marked `db`.
os.environ.setdefault("DATABASE_URL", "")
os.environ["INDIANKANOON_API_TOKEN"] = ""   # tests never call the paid API

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPO = Path(__file__).resolve().parents[2]


def _db_up() -> bool:
    try:
        from app.db import db_ok

        return db_ok()
    except Exception:
        return False


def pytest_collection_modifyitems(config, items):
    if any("db" in item.keywords for item in items) and not _db_up():
        skip = pytest.mark.skip(reason="Postgres not reachable")
        for item in items:
            if "db" in item.keywords:
                item.add_marker(skip)


@pytest.fixture(scope="session")
def corpus_dir() -> Path:
    return REPO / "corpus"


@pytest.fixture(scope="session")
def memory_repo(corpus_dir):
    from app.ingest.embedder import HashEmbedder
    from app.ingest.pipeline import build_memory_repo

    emb = HashEmbedder(1024)
    return build_memory_repo(corpus_dir, emb), emb
