import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from sqlalchemy import select

from app.check.pipeline import Deps, analyse, load_report, run_check
from app.config import REPO_DIR, settings
from app.corpus_repo import SqlCorpusRepo
from app.db import get_session
from app.errors import AppError
from app.ingest.embedder import get_embedder
from app.ingest.loaders import SUPPORTED, UnsupportedFile, load_text
from app.local_store import report_from_claims
from app.models import Check, Claim
from app.schemas import ApplyFixResult, CheckListItem, CheckRequest, Report, Summary

router = APIRouter(prefix="/api", tags=["checks"])
DEMO_DIR = REPO_DIR / "eval" / "drafts"


def _uuid(s: str) -> uuid.UUID:
    try:
        return uuid.UUID(s)
    except ValueError as e:
        raise AppError("NOT_FOUND", 404, "No such check") from e


async def _read_input(request: Request) -> tuple[str, str | None]:
    ctype = request.headers.get("content-type", "")
    if ctype.startswith("multipart/form-data"):
        form = await request.form()
        f = form.get("file")
        if f is None or not hasattr(f, "read"):
            raise AppError("INVALID_REQUEST", 422, "Send a 'file' field, or JSON {text, title}")
        name = f.filename or "draft.txt"
        if Path(name).suffix.lower() not in SUPPORTED:
            raise AppError("UNSUPPORTED_FILE", 415, "Upload a .txt, .docx or .pdf file")
        data = await f.read()
        if len(data) > settings.max_upload_mb * 1024 * 1024:
            raise AppError("DRAFT_TOO_LONG", 413, f"File is larger than {settings.max_upload_mb} MB")
        try:
            text = load_text(data, name)
        except UnsupportedFile as e:
            raise AppError("UNSUPPORTED_FILE", 415, str(e)) from e
        title = form.get("title")
        return text, (str(title) if title else Path(name).stem)
    try:
        body = CheckRequest.model_validate(await request.json())
    except (ValueError, ValidationError) as e:
        raise AppError("INVALID_REQUEST", 422, "Body must be JSON {text, title?} or a multipart file") from e
    return body.text, body.title


@router.post("/checks", response_model=Report)
async def create_check(request: Request, session=Depends(get_session)) -> Report:
    text, title = await _read_input(request)
    if not text.strip():
        raise AppError("INVALID_REQUEST", 422, "The draft is empty")
    if len(text) > settings.max_draft_chars:
        raise AppError("DRAFT_TOO_LONG", 413,
                       f"Draft has {len(text):,} characters; the limit is {settings.max_draft_chars:,}")
    state = request.app.state
    if session is None:                                   # no database: in-memory corpus + JSON files
        deps = Deps(repo=state.corpus.repo, embedder=get_embedder(), llm=state.llm, prism=state.prism,
                    online=state.online)
        claims, summary = await analyse(text, deps)
        report = report_from_claims(str(uuid.uuid4()), title, text, claims, summary, datetime.now(UTC))
        state.store.save(report)
        return report
    deps = Deps(repo=SqlCorpusRepo(session), embedder=get_embedder(), llm=state.llm, prism=state.prism,
                online=state.online)
    check_id = await run_check(session, deps, text, title)
    return load_report(session, check_id)


@router.get("/checks", response_model=list[CheckListItem])
def list_checks(request: Request, limit: int = 20, session=Depends(get_session)):
    if session is None:
        return request.app.state.store.list(min(limit, 100))
    rows = session.execute(select(Check).order_by(Check.created_at.desc()).limit(min(limit, 100))).scalars()
    return [CheckListItem(id=str(c.id), title=c.title, status=c.status, created_at=c.created_at,
                          summary=Summary(**c.summary) if c.summary else None) for c in rows]


@router.get("/checks/{check_id}", response_model=Report)
def get_check(request: Request, check_id: str, session=Depends(get_session)) -> Report:
    if session is None:
        rep = request.app.state.store.get(check_id)
    else:
        rep = load_report(session, _uuid(check_id))
    if rep is None:
        raise AppError("NOT_FOUND", 404, "No such check")
    return rep


def _apply(text: str, start: int, end: int, fix: dict | None, quote_text: str | None,
           citation_raw: str | None) -> ApplyFixResult:
    fix = fix or {}
    span = text[start:end]
    if fix.get("kind") == "replace_quote" and quote_text and fix.get("text"):
        old, new = quote_text, fix["text"]
    elif fix.get("kind") == "replace_citation" and citation_raw and fix.get("citation"):
        old, new = citation_raw, fix["citation"]
    else:
        raise AppError("INVALID_REQUEST", 422, "This claim has no automatic fix")
    if old in span:
        return ApplyFixResult(text=text[:start] + span.replace(old, new, 1) + text[end:])
    if old in text:
        return ApplyFixResult(text=text.replace(old, new, 1))
    raise AppError("INVALID_REQUEST", 422, "Could not locate the text to replace")


@router.post("/checks/{check_id}/claims/{claim_id}/apply-fix", response_model=ApplyFixResult)
def apply_fix(request: Request, check_id: str, claim_id: str, session=Depends(get_session)) -> ApplyFixResult:
    if session is None:
        rep = request.app.state.store.get(check_id)
        claim = next((c for c in rep.claims if c.id == claim_id), None) if rep else None
        if claim is None:
            raise AppError("NOT_FOUND", 404, "No such claim")
        return _apply(rep.input_text, claim.char_start, claim.char_end, claim.fix, claim.quote_text,
                      claim.citation_raw)
    check = session.get(Check, _uuid(check_id))
    row = session.get(Claim, _uuid(claim_id))
    if check is None or row is None or row.check_id != check.id:
        raise AppError("NOT_FOUND", 404, "No such claim")
    return _apply(check.input_text, row.char_start, row.char_end, row.fix, row.quote_text, row.citation_raw)


@router.get("/demo-drafts")
def demo_drafts() -> list[dict]:
    return [{"name": p.stem, "text": p.read_text(encoding="utf-8")}
            for p in sorted(DEMO_DIR.glob("*.txt"))]
