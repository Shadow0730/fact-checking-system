"""Step 5: hybrid search (vector + full-text), fused with reciprocal rank fusion."""
from collections.abc import Sequence

import numpy as np

from app.check.types import ChunkInfo


def rrf(*rankings: Sequence[int], k: int = 60) -> list[int]:
    score: dict[int, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking):
            score[cid] = score.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(score, key=lambda c: (-score[c], c))


def retrieve(repo, query: str, query_vec: np.ndarray, *, source_id: str | None = None,
             section: str | None = None, exclude_source: str | None = None,
             top_k: int = 5, candidates: int = 20, rrf_k: int = 60) -> list[ChunkInfo]:
    """If a statute section was cited, the evidence IS that section. Otherwise search inside the
    cited source (does the cited authority support the claim?) or the whole corpus."""
    if source_id and section:
        pinned = repo.chunks_by_para(source_id, section)
        if pinned:
            return pinned[:top_k]
    vec = repo.vector_search(query_vec, source_id, candidates, exclude_source=exclude_source)
    kw = repo.keyword_search(query, source_id, candidates, exclude_source=exclude_source)
    return repo.get_chunks(rrf(vec, kw, k=rrf_k)[:top_k])
