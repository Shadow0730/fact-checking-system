"""Step 3a: citations that are not in the local corpus are looked up on Indian Kanoon.

A search hit is never trusted on its title alone: the document is fetched and must contain the cited
citation (or, failing that, carry the cited case name, which the resolver then reports as a citation
mismatch). Found documents are written into corpus/files/indiankanoon/ and the manifest, so they are
part of the corpus from then on and are never paid for again.

Outcome per citation: "found" | "missing" (searched, nothing matched) | "error" (could not reach the API)
| "skipped" (over the per-check limit).
"""
import asyncio
import json
import re
from pathlib import Path

from rapidfuzz import fuzz

from app.check.citations import act_name_key, find_citations, parse_act_key
from app.check.normalize import norm_name
from app.check.resolver import _find_statute, resolve
from app.check.types import ClaimWork, Resolution
from app.clients.indiankanoon import IKUnavailable, strip_tags
from app.config import settings
from app.ingest.manifest import ManifestEntry, append_entry
from app.logging import get_logger

log = get_logger(__name__)
_write_lock = asyncio.Lock()
_YEAR = re.compile(r"\b(1[89]\d\d|20\d\d)\b")
_SECTION_TITLE = re.compile(r"^\s*Section\s+([0-9]+[A-Za-z]{0,2})\s+in\s+(.+?)\s*$", re.I)
NAME_MATCH = 92
ACT_MATCH = 88
MAX_DOCS_PER_CITATION = 3
IK_DIR = "files/indiankanoon"


def lookup_key(c: ClaimWork) -> str:
    return f"{c.citation_key or ''}|{norm_name(c.case_name or '')}"


def _title_name(title: str) -> str:
    """'A vs B on 12 March, 2018' -> 'A vs B'."""
    return re.split(r"\s+on\s+\d{1,2}\s+\w+,?\s+\d{4}", title or "")[0].strip()


def _year(s: str | None) -> int | None:
    m = _YEAR.search(s or "")
    return int(m.group(1)) if m else None


def _title_year(title: str) -> int | None:
    """The judgment date is at the end of an Indian Kanoon title, so take the last year."""
    ys = _YEAR.findall(title or "")
    return int(ys[-1]) if ys else None


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "act"


def _names_match(a: str, b: str) -> bool:
    a, b = norm_name(a), norm_name(b)
    if len(a.split()) < 2 or len(b.split()) < 2:
        return False
    return fuzz.token_set_ratio(a, b) >= NAME_MATCH


def _needs_lookup(repo, c: ClaimWork) -> bool:
    if c.claim_type == "fact" or not (c.citation_key or c.case_name) or c.citation_kind == "CONST":
        return False
    res = resolve(repo, c.citation_key, c.citation_kind, c.case_name)
    if c.citation_kind == "ACT":
        if res.status != "not_found":
            return False
        name, year, _ = parse_act_key(c.citation_key)  # type: ignore[misc]
        local = _find_statute(repo, name, year)
        return local is None or local.id.startswith("ik-")   # a curated local act is authoritative
    return res.status in ("not_found", "ambiguous")


# ── cases ─────────────────────────────────────────────────────────────────────
async def _lookup_case(ik, c: ClaimWork) -> dict | None:
    """Returns the verified document (with 'tid'), or None."""
    queries = []
    if c.citation_raw and c.citation_kind not in ("ACT", "CONST"):
        queries.append(f'"{c.citation_raw.strip()}"')
    if c.case_name:
        queries.append(re.sub(r"\s+v(?:s)?\.?\s+", " vs ", c.case_name))
    cite_year = _year(c.citation_raw)
    fetched: set[str] = set()
    for q in queries:
        hits = await ik.search(q, "judgments")
        ranked = []
        for h in hits[:8]:
            title = strip_tags(h.get("title", ""))
            name_ok = bool(c.case_name) and _names_match(c.case_name, _title_name(title))
            cite_ok = bool(c.citation_key) and c.citation_key in {
                x.key for x in find_citations(strip_tags(h.get("headline", "")) + " " + title)}
            ranked.append((cite_ok, name_ok, h))
        ranked.sort(key=lambda r: (not r[0], not r[1]))
        for i, (cite_ok, name_ok, h) in enumerate(ranked):
            if len(fetched) >= MAX_DOCS_PER_CITATION:
                return None
            tid = str(h["tid"])
            # Only spend a document fetch on a promising hit (or the top hit of a citation search).
            if tid in fetched or not (cite_ok or name_ok or (i == 0 and q.startswith('"'))):
                continue
            fetched.add(tid)
            d = await ik.doc(tid)
            text, title = d.get("text", ""), strip_tags(d.get("title") or h.get("title", ""))
            keys = {x.key for x in find_citations(text[:10000])}
            year = _title_year(title)
            year_ok = not (cite_year and year) or abs(cite_year - year) <= 1
            if (c.citation_key and c.citation_key in keys) or \
                    (c.case_name and _names_match(c.case_name, _title_name(title)) and year_ok):
                return {**d, "tid": tid, "title": title, "docsource": d.get("docsource") or h.get("docsource")}
    return None


def _case_entry(d: dict, corpus: Path) -> ManifestEntry:
    tid, title, text = d["tid"], d["title"], d["text"]
    cites, seen = [], set()
    for x in find_citations(text[:10000]):
        if x.is_case and x.key not in seen:
            seen.add(x.key)
            cites.append(x.raw)
    rel = f"{IK_DIR}/ik-{tid}.txt"
    path = corpus / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    header = f"Source: Indian Kanoon, https://indiankanoon.org/doc/{tid}/\n\n"
    path.write_text(header + text, encoding="utf-8")
    name = _title_name(title)
    return ManifestEntry(id=f"ik-{tid}", title=name or title, doc_type="judgment",
                         court=strip_tags(d.get("docsource") or "") or None, year=_title_year(title),
                         citations=cites[:10], aliases=[name] if name else [], file=rel, enabled=True)


# ── statutes ──────────────────────────────────────────────────────────────────
async def _lookup_section(ik, c: ClaimWork) -> tuple[str, str, str] | None:
    """Returns (act title, section, section text) or None."""
    name, year, section = parse_act_key(c.citation_key)  # type: ignore[misc]
    want = re.sub(r"\b\d{4}\b", "", name).strip()
    hits = await ik.search(f'"Section {section}" {want}', "laws")
    for h in hits[:8]:
        m = _SECTION_TITLE.match(strip_tags(h.get("title", "")))
        if not m or m.group(1).upper() != section.upper():
            continue
        act = m.group(2).strip()
        if fuzz.token_sort_ratio(want, re.sub(r"\b\d{4}\b", "", act_name_key(act)).strip()) < ACT_MATCH:
            continue
        if year and _year(act) and str(_year(act)) != year:
            continue
        d = await ik.doc(h["tid"])
        lines = [ln for ln in d.get("text", "").splitlines() if ln.strip()]
        if lines and _SECTION_TITLE.match(lines[0]):
            lines = lines[1:]
        body = " ".join(" ".join(lines).split())
        body = re.sub(rf"^(?:Section\s+)?{re.escape(section)}\s*\.?\s*", "", body, flags=re.I)
        if body:
            return act, section, f"{body} [Indian Kanoon: https://indiankanoon.org/doc/{h['tid']}/]"
    return None


def _sec_sort(s: str) -> tuple[int, str]:
    m = re.match(r"(\d+)([A-Z]*)", s.upper())
    return (int(m.group(1)), m.group(2)) if m else (0, s)


def _act_entry(act: str, section: str, body: str, corpus: Path) -> ManifestEntry:
    sid = f"ik-act-{_slug(act_name_key(act))}"
    rel = f"{IK_DIR}/{sid}.txt"
    side = corpus / f"{IK_DIR}/{sid}.json"
    side.parent.mkdir(parents=True, exist_ok=True)
    sections = json.loads(side.read_text(encoding="utf-8")) if side.exists() else {}
    sections[section.upper()] = body
    side.write_text(json.dumps(sections, ensure_ascii=False, indent=1), encoding="utf-8")
    text = f"{act} (sections fetched from Indian Kanoon)\n\n" + "\n\n".join(
        f"{s}. {sections[s]}" for s in sorted(sections, key=_sec_sort))
    (corpus / rel).write_text(text, encoding="utf-8")
    base = re.sub(r",?\s*\b\d{4}\b", "", act).strip()
    return ManifestEntry(id=sid, title=act, doc_type="statute", year=_year(act),
                         aliases=[base] if base != act else [], file=rel, enabled=True)


# ── orchestration ─────────────────────────────────────────────────────────────
async def _lookup_one(deps, c: ClaimWork) -> str:
    ik, corpus = deps.online, settings.corpus_path
    try:
        if c.citation_kind == "ACT":
            hit = await _lookup_section(ik, c)
            if hit is None:
                return "missing"
            async with _write_lock:
                entry = _act_entry(*hit, corpus)
                append_entry(corpus, entry)
                deps.repo.add_entry(entry, corpus, deps.embedder)
        else:
            d = await _lookup_case(ik, c)
            if d is None:
                return "missing"
            async with _write_lock:
                entry = _case_entry(d, corpus)
                append_entry(corpus, entry)
                deps.repo.add_entry(entry, corpus, deps.embedder)
        log.info("added from indian kanoon", extra={"kv": {"source": entry.id, "citation": c.citation_raw}})
        return "found"
    except IKUnavailable as e:
        log.warning("indian kanoon unavailable", extra={"kv": {"error": str(e)}})
        return "error"


async def lookup_missing(deps, claims: list[ClaimWork]) -> dict[str, str]:
    """Look up every distinct missing citation (up to the per-check limit). Returns {lookup_key: outcome}."""
    if getattr(deps, "online", None) is None:
        return {}
    todo: dict[str, ClaimWork] = {}
    outcome: dict[str, str] = {}
    for c in claims:
        k = lookup_key(c)
        if k in todo or k in outcome or not _needs_lookup(deps.repo, c):
            continue
        if len(todo) >= settings.indiankanoon_max_lookups:
            outcome[k] = "skipped"
        else:
            todo[k] = c
    results = await asyncio.gather(*(_lookup_one(deps, c) for c in todo.values()))
    outcome.update(zip(todo.keys(), results))
    return outcome


def annotate(c: ClaimWork, outcome: dict[str, str]) -> None:
    """After resolving: explain what the online lookup did for a citation that is still missing."""
    o = outcome.get(lookup_key(c))
    if not o or c.resolution.status not in ("not_found", "ambiguous"):
        return
    if o == "error":
        c.resolution = Resolution("unverified", section=c.resolution.section,
                                  note="It is not in the local source database, and Indian Kanoon could not be "
                                       "reached to check it.")
    elif o == "missing" and c.resolution.status == "not_found":
        extra = "It was also not found on Indian Kanoon."
        c.resolution.note = f"{c.resolution.note} {extra}" if c.resolution.note else extra
    elif o == "skipped" and c.resolution.status == "not_found":
        c.resolution = Resolution("unverified", section=c.resolution.section,
                                  note="It is not in the local source database and was not looked up online "
                                       "(per-check lookup limit reached).")
