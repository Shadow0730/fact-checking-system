"""Pydantic request/response models: the API contract. Mirrored in frontend/lib/types.ts."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["verified", "weak", "insufficient", "misquote", "contradicted", "fabricated", "not_legal"]
Colour = Literal["green", "amber", "red", "grey"]
ClaimType = Literal["holding", "statutory", "quote", "fact"]


# ── Claim extraction (LLM output) ────────────────────────────────────────────
class ExtractedClaim(BaseModel):
    sentence_ids: list[str] = Field(min_length=1)
    text: str
    claim_type: ClaimType
    citation: str | None = None
    case_name: str | None = None
    quote: str | None = None


class ClaimList(BaseModel):
    claims: list[ExtractedClaim]


# ── Requests ─────────────────────────────────────────────────────────────────
class CheckRequest(BaseModel):
    text: str
    title: str | None = None


class SourceMeta(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9\-_]{1,80}$")
    title: str
    doc_type: Literal["judgment", "statute", "rules", "circular"]
    court: str | None = None
    year: int | None = None
    language: str = "en"
    citations: list[str] = []
    aliases: list[str] = []
    sectioning: Literal["judgment", "statute"] | None = None


# ── Responses ────────────────────────────────────────────────────────────────
class SourceRef(BaseModel):
    id: str
    title: str
    citations: list[str] = []


class Evidence(BaseModel):
    chunk_id: int
    source_id: str
    source_title: str
    para: str | None = None
    page_start: int | None = None
    text: str


class DiffOp(BaseModel):
    op: Literal["equal", "replace", "delete", "insert"]
    draft: str
    source: str


class ClaimOut(BaseModel):
    id: str
    ord: int
    char_start: int
    char_end: int
    text: str
    claim_type: ClaimType
    citation_raw: str | None = None
    citation_key: str | None = None
    citation_status: str | None = None
    case_name: str | None = None
    source: SourceRef | None = None
    quote_text: str | None = None
    quote_score: float | None = None
    quote_match: str | None = None
    quote_diff: list[DiffOp] | None = None
    quote_critical: bool | None = None
    support_probs: dict[str, float] | None = None
    evidence: Evidence | None = None
    verdict: Verdict
    colour: Colour
    confidence: float | None = None
    reason: str
    fix: dict | None = None


class Summary(BaseModel):
    claims: int = 0
    verified: int = 0
    weak: int = 0
    insufficient: int = 0
    misquote: int = 0
    contradicted: int = 0
    fabricated: int = 0
    not_legal: int = 0
    seconds: float = 0.0
    prism_input_tokens: int = 0
    llm_tokens: int = 0
    cost_inr: float = 0.0
    offline_mode: bool = False
    online_lookups: int = 0
    online_found: int = 0


class Report(BaseModel):
    id: str
    title: str | None = None
    status: str
    input_text: str
    summary: Summary | None = None
    error: str | None = None
    created_at: datetime | None = None
    claims: list[ClaimOut] = []


class CheckListItem(BaseModel):
    id: str
    title: str | None
    status: str
    created_at: datetime
    summary: Summary | None


class SourceOut(BaseModel):
    id: str
    title: str
    doc_type: str
    court: str | None
    year: int | None
    language: str
    citations: list[str]
    citation_keys: list[str]
    chunks: int


class IngestResult(BaseModel):
    id: str
    chunks: int
    skipped: bool = False


class ApplyFixResult(BaseModel):
    text: str


class Health(BaseModel):
    db: str
    embedding_model: str
    embedding_loaded: bool
    sources: int
    chunks: int
    offline_mode: bool
    online_lookup: bool = False


class ErrorBody(BaseModel):
    code: str
    message: str
