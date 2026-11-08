"""Plain data types passed between the pipeline steps (no DB, no I/O)."""
from dataclasses import dataclass, field


@dataclass
class SourceInfo:
    id: str
    title: str
    doc_type: str
    court: str | None = None
    year: int | None = None
    citations: list[str] = field(default_factory=list)
    citation_keys: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)


@dataclass
class ChunkInfo:
    id: int
    source_id: str
    source_title: str
    ord: int
    text: str
    para: str | None = None
    page_start: int | None = None
    page_end: int | None = None


@dataclass
class Citation:
    raw: str
    key: str
    kind: str          # AIR | SCC | SCR | INSC | ACT | CONST
    char_start: int
    char_end: int

    @property
    def is_case(self) -> bool:
        return self.kind in {"AIR", "SCC", "SCR", "INSC"}


@dataclass
class Quote:
    text: str
    char_start: int
    char_end: int


@dataclass
class Sentence:
    id: str            # "S1"
    text: str
    char_start: int
    char_end: int


@dataclass
class Resolution:
    status: str                         # found | not_found | ambiguous | unverified | none
    source: SourceInfo | None = None
    section: str | None = None          # for statute/constitution citations
    note: str | None = None             # e.g. "did you mean ...?"
    mismatch: bool = False              # case name matched but citation number did not


@dataclass
class QuoteResult:
    score: float
    match: str
    chunk_id: int | None
    diff: list[dict]
    critical: bool
    has_diff: bool


@dataclass
class ClaimWork:
    """One claim as it moves through steps 2-8."""
    ord: int
    text: str
    claim_type: str
    char_start: int
    char_end: int
    citation_raw: str | None = None
    citation_key: str | None = None
    citation_kind: str | None = None
    case_name: str | None = None
    quote_text: str | None = None
    # step 3
    resolution: Resolution = field(default_factory=lambda: Resolution("none"))
    # step 4
    quote: QuoteResult | None = None
    # step 5
    passages: list[ChunkInfo] = field(default_factory=list)
    # step 6
    support_probs: dict[str, float] | None = None
    evidence: ChunkInfo | None = None
    prism_tokens: int = 0
    # step 7
    verdict: str = "insufficient"
    colour: str = "amber"
    confidence: float | None = None
    reason: str = ""
    # step 8
    fix: dict | None = None
    alternative: tuple[SourceInfo, ChunkInfo, float] | None = None

    @property
    def citation_status(self) -> str:
        return self.resolution.status

    @property
    def source(self) -> SourceInfo | None:
        return self.resolution.source

    @property
    def p_supported(self) -> float:
        return (self.support_probs or {}).get("supported", 0.0)

    @property
    def p_contradicted(self) -> float:
        return (self.support_probs or {}).get("contradicted", 0.0)
