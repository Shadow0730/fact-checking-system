"""run_check(text): orchestrates steps 1-8 and saves the Check + Claims.

`analyse()` does the work against any CorpusRepo and is DB-free apart from the repo itself,
so tests run it on an in-memory corpus. `run_check()` adds persistence.
"""
import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.check.citations import find_citations
from app.check.extractor import extract_claims
from app.check.fixer import suggest_fix
from app.check.judge import judge, judge_passages
from app.check.online import annotate, lookup_missing
from app.check.quotes import QUOTE_RELATED, find_quotes, verify_quote
from app.check.resolver import resolve
from app.check.retriever import retrieve
from app.check.scorer import Thresholds, score
from app.check.segmenter import segment
from app.check.types import ChunkInfo, ClaimWork
from app.config import settings
from app.logging import get_logger

log = get_logger(__name__)
PRISM_INR_PER_TOKEN = 4 / 1_000_000
VERDICTS = ("verified", "weak", "insufficient", "misquote", "contradicted", "fabricated", "not_legal")


@dataclass
class Deps:
    repo: object        # CorpusRepo
    embedder: object    # .embed(list[str]) -> np.ndarray
    llm: object | None
    prism: object
    online: object | None = None          # IndianKanoon client, or None (local corpus only)
    lookups: dict = field(default_factory=dict)   # {lookup key: found|missing|error|skipped}, last check


def _retrieve(deps: Deps, c: ClaimWork, vec, **kw) -> list[ChunkInfo]:
    return retrieve(deps.repo, c.text, vec, top_k=settings.retrieval_top_k,
                    candidates=settings.retrieval_candidates, rrf_k=settings.rrf_k, **kw)


def _quote_chunks(deps: Deps, c: ClaimWork) -> list[ChunkInfo]:
    if c.source:
        return deps.repo.chunks_of(c.source.id)
    # No resolved citation: check the quote inside the sources the passages came from.
    seen: list[str] = []
    for p in c.passages:
        if p.source_id not in seen:
            seen.append(p.source_id)
    return [ch for sid in seen[:2] for ch in deps.repo.chunks_of(sid)]


async def check_claims(deps: Deps, claims: list[ClaimWork], th: Thresholds) -> None:
    """Steps 3-8 for already-extracted claims (also used directly by the evaluation)."""
    deps.lookups = await lookup_missing(deps, claims)                        # step 3a (online)
    for c in claims:                                                         # step 3
        if c.claim_type != "fact":
            c.resolution = resolve(deps.repo, c.citation_key, c.citation_kind, c.case_name)
            annotate(c, deps.lookups)

    legal = [c for c in claims if c.claim_type != "fact"]
    vecs = deps.embedder.embed([c.text for c in legal]) if legal else []
    vec_of = {id(c): v for c, v in zip(legal, vecs)}
    for c in legal:
        v = vec_of[id(c)]
        c.passages = _retrieve(deps, c, v, source_id=c.source.id if c.source else None,  # step 5
                               section=c.resolution.section if c.source else None)
        if c.quote_text:                                                     # step 4
            chunks = _quote_chunks(deps, c)
            if chunks:
                c.quote = verify_quote(c.quote_text, chunks)
                if c.source is None and c.quote.score < QUOTE_RELATED:
                    # No cited source and nothing similar in the corpus: we can't say what it quotes,
                    # so don't call it a misquote of an unrelated passage. The claim is judged as usual.
                    c.quote = None

    await asyncio.gather(*(judge(deps.prism, c) for c in legal))            # step 6

    for c in claims:                                                         # step 7
        score(c, th)

    # "Not supported by the case you cited, but supported by X": a second, whole-corpus look.
    need_alt = [c for c in legal if c.source and c.verdict in ("contradicted", "weak", "insufficient")]
    for c in legal:
        if c.verdict == "fabricated" and c.evidence and c.p_supported >= th.supported:
            src = deps.repo.get_source(c.evidence.source_id)
            if src:
                c.alternative = (src, c.evidence, c.p_supported)

    async def alt(c: ClaimWork) -> None:
        used = {p.id for p in c.passages}
        extra = retrieve(deps.repo, c.text, vec_of[id(c)], top_k=settings.retrieval_top_k + len(used),
                         candidates=settings.retrieval_candidates, rrf_k=settings.rrf_k)
        extra = [p for p in extra if p.id not in used][: settings.retrieval_top_k]
        if not extra:
            return
        probs, ev, tokens = await judge_passages(deps.prism, c.text, None, extra)
        c.prism_tokens += tokens
        if ev and probs["supported"] >= th.supported:
            src = deps.repo.get_source(ev.source_id)
            if src:
                c.alternative = (src, ev, probs["supported"])

    await asyncio.gather(*(alt(c) for c in need_alt))
    for c in claims:                                                         # step 8
        c.fix = suggest_fix(c)


async def analyse(text: str, deps: Deps, th: Thresholds | None = None) -> tuple[list[ClaimWork], dict]:
    th = th or Thresholds.from_settings()
    t0 = time.perf_counter()
    sentences = segment(text)                                                # step 1
    cites = find_citations(text)                                             # step 2a
    quotes = find_quotes(text)                                               # step 2b
    claims, llm_tokens = await extract_claims(deps.llm, text, sentences, cites, quotes)  # step 2c
    await check_claims(deps, claims, th)
    prism_tokens = sum(c.prism_tokens for c in claims)
    summary = {"claims": len(claims), **{v: sum(c.verdict == v for c in claims) for v in VERDICTS},
               "seconds": round(time.perf_counter() - t0, 2), "prism_input_tokens": prism_tokens,
               "llm_tokens": llm_tokens, "cost_inr": round(prism_tokens * PRISM_INR_PER_TOKEN, 4),
               "offline_mode": settings.offline_mode,
               "online_lookups": len(deps.lookups),
               "online_found": sum(v == "found" for v in deps.lookups.values())}
    return claims, summary


# ── persistence ──────────────────────────────────────────────────────────────
def _claim_row(check_id: uuid.UUID, c: ClaimWork):
    from app.models import Claim

    q = c.quote
    return Claim(
        check_id=check_id, ord=c.ord, char_start=c.char_start, char_end=c.char_end, text=c.text,
        claim_type=c.claim_type, citation_raw=c.citation_raw, citation_key=c.citation_key,
        citation_status=c.citation_status, case_name=c.case_name,
        source_id=c.source.id if c.source else None, quote_text=c.quote_text,
        quote_score=q.score if q else None, quote_match=q.match if q else None,
        quote_diff=q.diff if q else None, quote_critical=q.critical if q else None,
        support_probs=c.support_probs, evidence_chunk=c.evidence.id if c.evidence else None,
        verdict=c.verdict, colour=c.colour, confidence=c.confidence, reason=c.reason, fix=c.fix,
    )


async def run_check(session, deps: Deps, text: str, title: str | None) -> uuid.UUID:
    from app.models import Check

    check = Check(id=uuid.uuid4(), title=title, input_text=text, status="running")
    session.add(check)
    session.commit()
    try:
        claims, summary = await analyse(text, deps)
        session.add_all([_claim_row(check.id, c) for c in claims])
        check.status, check.summary = "done", summary
    except Exception as e:
        log.exception("check failed")
        check.status, check.error = "failed", str(e)[:2000]
        check.finished_at = datetime.now(UTC)
        session.commit()
        raise
    check.finished_at = datetime.now(UTC)
    session.commit()
    return check.id


def load_report(session, check_id: uuid.UUID):
    from sqlalchemy import select

    from app.models import Check, Chunk, Claim, Source
    from app.schemas import ClaimOut, Evidence, Report, SourceRef, Summary

    check = session.get(Check, check_id)
    if check is None:
        return None
    rows = session.execute(select(Claim).where(Claim.check_id == check_id).order_by(Claim.ord)).scalars().all()
    src_ids = {r.source_id for r in rows if r.source_id}
    chunk_ids = {r.evidence_chunk for r in rows if r.evidence_chunk}
    sources = {s.id: s for s in session.execute(select(Source).where(Source.id.in_(src_ids))).scalars()} \
        if src_ids else {}
    chunks = {c.id: c for c in session.execute(select(Chunk).where(Chunk.id.in_(chunk_ids))).scalars()} \
        if chunk_ids else {}
    titles = dict(session.execute(select(Source.id, Source.title)).all()) if chunks else {}

    out = []
    for r in rows:
        s = sources.get(r.source_id)
        ch = chunks.get(r.evidence_chunk)
        out.append(ClaimOut(
            id=str(r.id), ord=r.ord, char_start=r.char_start, char_end=r.char_end, text=r.text,
            claim_type=r.claim_type, citation_raw=r.citation_raw, citation_key=r.citation_key,
            citation_status=r.citation_status, case_name=r.case_name,
            source=SourceRef(id=s.id, title=s.title, citations=list(s.citations or [])) if s else None,
            quote_text=r.quote_text, quote_score=r.quote_score, quote_match=r.quote_match,
            quote_diff=r.quote_diff, quote_critical=r.quote_critical, support_probs=r.support_probs,
            evidence=Evidence(chunk_id=ch.id, source_id=ch.source_id, source_title=titles.get(ch.source_id, ""),
                              para=ch.para, page_start=ch.page_start, text=ch.text) if ch else None,
            verdict=r.verdict, colour=r.colour, confidence=r.confidence, reason=r.reason, fix=r.fix,
        ))
    return Report(id=str(check.id), title=check.title, status=check.status, input_text=check.input_text,
                  summary=Summary(**check.summary) if check.summary else None, error=check.error,
                  created_at=check.created_at, claims=out)
