"""Step 7: verdict rules + thresholds. Rules are applied in order; the first match wins."""
from dataclasses import asdict, dataclass

from app.check.quotes import quote_is_exact
from app.check.types import ChunkInfo, ClaimWork
from app.config import settings


@dataclass(frozen=True)
class Thresholds:
    supported: float
    weak: float
    contradicted: float
    quote_exact: float
    quote_near: float

    @classmethod
    def from_settings(cls) -> "Thresholds":
        return cls(settings.thresh_supported, settings.thresh_weak, settings.thresh_contradicted,
                   settings.quote_exact, settings.quote_near)

    def as_dict(self) -> dict:
        return asdict(self)


def where(ev: ChunkInfo | None, with_source: bool = False) -> str:
    if ev is None:
        return "the passage shown"
    if ev.para:
        label = f"para {ev.para}"
        if ev.para[:1].isdigit() and any(w in ev.source_title.lower() for w in ("act", "rules", "constitution")):
            label = f"{'Article' if 'constitution' in ev.source_title.lower() else 'Section'} {ev.para}"
    else:
        label = "the passage shown"
    return f"{ev.source_title}, {label}" if with_source else label


def describe_diff(diff: list[dict]) -> str:
    for op in diff:
        if op["op"] == "replace":
            return f"'{op['draft']}' in the draft is '{op['source']}' in the source"
        if op["op"] == "delete":
            return f"'{op['draft']}' does not appear in the source"
        if op["op"] == "insert":
            return f"the source also says '{op['source']}'"
    return ""


def score(c: ClaimWork, th: Thresholds) -> None:
    c.confidence = round(c.p_supported, 4) if c.support_probs is not None else None
    res = c.resolution
    cited = bool(c.citation_raw or c.case_name)
    q = c.quote

    def done(verdict: str, colour: str, reason: str) -> None:
        if res.note and res.status in ("ambiguous", "not_found") and res.note not in reason:
            reason = f"{reason} {res.note}"
        c.verdict, c.colour, c.reason = verdict, colour, reason

    # 1. not a legal claim
    if c.claim_type == "fact":
        return done("not_legal", "grey", "A fact about this matter, not checkable against the law.")
    # 2. citation given but not in the corpus
    if cited and res.status == "not_found":
        return done("fabricated", "red",
                    "This citation was not found in the source database: possibly fabricated.")
    # 2b. could not be checked online (Indian Kanoon unreachable / lookup limit): never call it fabricated
    if cited and res.status == "unverified":
        return done("insufficient", "amber", f"Could not verify this citation. {res.note or ''}".strip())
    # 3. misquote
    if c.quote_text and q is not None and (q.score < th.quote_near or q.critical):
        detail = describe_diff(q.diff) if q.score >= th.quote_near or q.critical else ""
        reason = "The quoted text doesn't match the source" + (f": {detail}." if detail else ".")
        if q.critical and q.score >= th.quote_near:
            reason += " A word that changes legal meaning differs."
        return done("misquote", "red", reason)
    # 4. contradicted
    if c.p_contradicted >= th.contradicted:
        who = "The cited source" if c.source else "The sources"
        return done("contradicted", "red", f"{who} says otherwise ({where(c.evidence, not c.source)}).")
    # 4b. quote with minor (non-critical) differences
    if c.quote_text and q is not None and not quote_is_exact(q, th.quote_exact):
        return done("weak", "amber", f"The quote has minor differences from the source: {describe_diff(q.diff)}.")
    # 5. verified
    if c.p_supported >= th.supported:
        if res.mismatch:
            return done("weak", "amber", f"Supported by {where(c.evidence, True)}. {res.note}")
        tail = "" if cited else " (no citation given in the draft)"
        return done("verified", "green", f"Supported by {where(c.evidence, True)}{tail}.")
    # 6. weak support
    if c.p_supported >= th.weak:
        reason = f"Partly supported; check {where(c.evidence, True)}."
        if res.mismatch:
            reason += f" {res.note}"
        return done("weak", "amber", reason)
    # 7. abstain
    return done("insufficient", "amber", "Not enough in the sources to confirm this. Not verified.")
