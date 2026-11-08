"""Step 2c: claim extraction. Sentence ids in, claims out (Sarvam LLM), or a regex fallback."""
import json
import re
from pathlib import Path

from pydantic import ValidationError

from app.check.citations import citation_key
from app.check.types import Citation, ClaimWork, Quote, Sentence
from app.clients.sarvam_llm import LLMJSONError
from app.config import settings
from app.logging import get_logger
from app.schemas import ClaimList, ExtractedClaim

log = get_logger(__name__)
PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "extract_claims.md"
BATCH_SENTENCES = 60

_LEGAL = re.compile(r"\b(held|holds|observed|ruled|court|section|sec\.|article|act|rules?|liable|"
                    r"offence|provision|statute|judgment|presum\w*|mandatory|limitation|cognizance)\b", re.I)
_CASE_NAME = re.compile(
    r"((?:[A-Z][\w.&'/-]*\s+){0,6}?[A-Z][\w.&'/-]*\s+v(?:s)?\.?\s+(?:[A-Z][\w.&'/-]*\.?\s*){1,8}?)"
    r"(?=,|\s*\(|\s*\[|\s+AIR\b|\s+\d{4}\s+INSC)"
)


def system_prompt() -> str:
    schema = json.dumps(ClaimList.model_json_schema(), indent=1)
    return PROMPT_PATH.read_text(encoding="utf-8").replace("{schema}", schema)


def user_message(sentences: list[Sentence], cites: list[Citation]) -> str:
    def sid_of(pos: int) -> str:
        return next((s.id for s in sentences if s.char_start <= pos < s.char_end), "?")

    lines = ["CITATIONS FOUND BY PARSER:"]
    lines += [f"- {c.raw}  [{sid_of(c.char_start)}]" for c in cites] or ["- (none)"]
    lines += ["", "SENTENCES:"]
    lines += [f"{s.id}: {s.text}" for s in sentences]
    return "\n".join(lines)


def pick_citation(cites: list[Citation], claim_type: str) -> Citation | None:
    if not cites:
        return None
    cases = [c for c in cites if c.is_case]
    laws = [c for c in cites if not c.is_case]
    first, second = (laws, cases) if claim_type == "statutory" else (cases, laws)
    return (first or second)[0]


# A quotation is only checked against the corpus if the sentence attributes it to an authority.
# Without this, any phrase in quote marks (a defined term, a project description in a contract)
# was treated as a quotation from the law and compared with an unrelated passage.
_ATTRIBUTION = re.compile(r"\b(held|holds|observed|ruled|opined|laid down|provides?|provided|reads?|states?|"
                          r"stipulates?|declares?|mandates?|in the words of|per|court|bench|judgment|"
                          r"section|sec\.|article|art\.|act|rules?|regulations?|code)\b", re.I)


def is_attributed(text: str, has_citation: bool, case_name: str | None) -> bool:
    return has_citation or bool(case_name) or bool(_ATTRIBUTION.search(text))


def _within(start: int, end: int, items):
    return [x for x in items if x.char_start < end and x.char_end > start]


def _build(ord_: int, text: str, ctype: str, start: int, end: int, cites: list[Citation],
           quotes: list[Quote], llm_citation: str | None = None, case_name: str | None = None,
           llm_quote: str | None = None) -> ClaimWork:
    qs = _within(start, end, quotes)
    if qs:     # the claim must cover its whole quotation
        start, end = min(start, qs[0].char_start), max(end, qs[0].char_end)
    in_span = _within(start, end, cites)
    chosen = pick_citation(in_span, ctype)
    raw, key, kind = (chosen.raw, chosen.key, chosen.kind) if chosen else (None, None, None)
    if llm_citation and not chosen:
        k = citation_key(llm_citation)
        raw, key, kind = llm_citation, k, (k.split("|")[0] if k else None)
    quote_text = qs[0].text if qs else (llm_quote or None)
    if quote_text and not is_attributed(text, bool(raw), case_name):
        quote_text = None                        # quote marks, but not a quotation of any authority
        if ctype == "quote":
            ctype = "fact"
    if ctype == "quote" and not quote_text:
        ctype = "holding"
    return ClaimWork(ord=ord_, text=text, claim_type=ctype, char_start=start, char_end=end,
                     citation_raw=raw, citation_key=key, citation_kind=kind,
                     case_name=case_name, quote_text=quote_text)


def find_case_name(text: str) -> str | None:
    m = _CASE_NAME.search(text)
    if not m:
        return None
    name = m.group(1).strip().rstrip(",")
    name = re.sub(r"^(?:In|in|See|see|Also|also|The|the|Per|per)\s+", "", name)
    return name or None


def heuristic_extract(text: str, sentences: list[Sentence], cites: list[Citation],
                      quotes: list[Quote]) -> list[ClaimWork]:
    """Offline / fallback: every sentence with a citation, a quote or legal wording is a claim."""
    claims: list[ClaimWork] = []
    covered_until = -1
    for s in sentences:
        if s.char_end <= covered_until:
            continue
        sc = _within(s.char_start, s.char_end, cites)
        sq = _within(s.char_start, s.char_end, quotes)
        if sq and not is_attributed(s.text, bool(sc), find_case_name(s.text)):
            sq = []                              # e.g. a defined term or description in a contract
        if not (sc or sq or _LEGAL.search(s.text)):
            continue
        if not sq and (s.text.isupper() or len(s.text.split()) < 5):   # headings
            continue
        if sq:
            ctype = "quote"
        elif sc and all(not c.is_case for c in sc):
            ctype = "statutory"
        elif sc:
            ctype = "holding"
        elif re.search(r"\b(Section|Article|Act|Rules?)\b", s.text):
            ctype = "statutory"
        else:
            ctype = "holding"
        c = _build(len(claims) + 1, s.text, ctype, s.char_start, s.char_end, cites, quotes,
                   case_name=find_case_name(s.text))
        if (c.char_start, c.char_end) != (s.char_start, s.char_end):   # widened to cover a quote
            c.text = text[c.char_start:c.char_end]
        covered_until = c.char_end
        claims.append(c)
    return claims


def _to_work(ec: ExtractedClaim, ord_: int, text: str, by_id: dict[str, Sentence],
             cites: list[Citation], quotes: list[Quote]) -> ClaimWork | None:
    sents = [by_id[i] for i in ec.sentence_ids if i in by_id]
    if not sents:
        return None
    start, end = min(s.char_start for s in sents), max(s.char_end for s in sents)
    at = text.find(ec.text.strip(), start, end) if ec.text.strip() else -1
    if at >= 0:                              # narrow to the claim itself when copied verbatim
        start, end = at, at + len(ec.text.strip())
    case_name = ec.case_name or find_case_name(text[start:end])
    return _build(ord_, ec.text.strip() or text[start:end], ec.claim_type, start, end, cites, quotes,
                  llm_citation=ec.citation, case_name=case_name, llm_quote=ec.quote)


async def extract_claims(llm, text: str, sentences: list[Sentence], cites: list[Citation],
                         quotes: list[Quote]) -> tuple[list[ClaimWork], int]:
    """Returns (claims, llm_tokens)."""
    if settings.offline_mode or llm is None:
        return heuristic_extract(text, sentences, cites, quotes), 0

    system = system_prompt()
    by_id = {s.id: s for s in sentences}
    tokens = 0
    extracted: list[ExtractedClaim] = []
    for i in range(0, len(sentences), BATCH_SENTENCES):
        batch = sentences[i:i + BATCH_SENTENCES]
        lo, hi = batch[0].char_start, batch[-1].char_end
        user = user_message(batch, _within(lo, hi, cites))
        for attempt in range(2):
            try:
                data, t = await llm.chat_json(system, user)
                tokens += t
                extracted += ClaimList.model_validate(data).claims
                break
            except (LLMJSONError, ValidationError) as e:
                log.warning("claim extraction returned invalid JSON", extra={"kv": {"attempt": attempt, "err": str(e)[:300]}})
                if attempt == 1:     # fall back for this batch rather than fail the whole check
                    extracted_batch = heuristic_extract(text, batch, cites, quotes)
                    extracted += [ExtractedClaim(sentence_ids=[s.id for s in batch
                                                               if s.char_start < c.char_end and s.char_end > c.char_start],
                                                 text=c.text, claim_type=c.claim_type)
                                  for c in extracted_batch]
                user += "\n\nYour previous reply was not valid JSON for the schema. Reply with the JSON object only."

    claims: list[ClaimWork] = []
    seen: set[tuple[int, int, str]] = set()
    for ec in extracted:
        w = _to_work(ec, len(claims) + 1, text, by_id, cites, quotes)
        if w is None:
            continue
        sig = (w.char_start, w.char_end, w.text)
        if sig in seen:
            continue
        seen.add(sig)
        claims.append(w)
    return claims, tokens
