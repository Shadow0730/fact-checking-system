"""Step 3: citation key -> source, or NOT_FOUND / AMBIGUOUS. No AI guessing.

`not_found` means "not in OUR corpus", never proof that a case is fake.
"""
import re

from rapidfuzz import fuzz, process

from app.check.citations import act_name_key, parse_act_key
from app.check.normalize import norm_name
from app.check.types import Resolution, SourceInfo

NAME_FOUND = 92
NAME_AMBIGUOUS = 80
ACT_FOUND = 88


def _match_name(repo, name: str) -> tuple[SourceInfo | None, float]:
    rows = repo.alias_index()
    if not rows or not name:
        return None, 0.0
    hit = process.extractOne(norm_name(name), [a for a, _ in rows], scorer=fuzz.token_set_ratio)
    if not hit:
        return None, 0.0
    _, score, idx = hit
    return repo.get_source(rows[idx][1]), float(score)


def _strip_year(name: str) -> str:
    return re.sub(r"\b\d{4}\b", "", name).strip()


def _find_statute(repo, act_name: str, year: str, want_constitution: bool = False) -> SourceInfo | None:
    best, best_score = None, 0.0
    target = _strip_year(act_name_key(act_name))
    for s in repo.sources(["statute", "rules"]):
        names = [s.title, *s.aliases]
        if want_constitution:
            if any("constitution" in n.lower() for n in names):
                return s
            continue
        for n in names:
            score = fuzz.token_sort_ratio(target, _strip_year(act_name_key(n)))
            if score > best_score:
                best, best_score = s, score
    if best is None or best_score < ACT_FOUND:
        return None
    if year and best.year and str(best.year) != year:
        return None
    return best


def resolve(repo, key: str | None, kind: str | None, case_name: str | None) -> Resolution:
    if not key and not case_name:
        return Resolution("none")

    # Statutes and the Constitution: match the act by name, then the section must exist.
    if kind in ("ACT", "CONST") and key:
        if kind == "ACT":
            name, year, section = parse_act_key(key)  # type: ignore[misc]
            src = _find_statute(repo, name, year)
            label = f"Section {section}"
        else:
            section = key.split("|")[2]
            src = _find_statute(repo, "", "", want_constitution=True)
            label = f"Article {section}"
        if src is None:
            return Resolution("not_found", note="This statute is not in the source database.")
        if not repo.chunks_by_para(src.id, section):
            return Resolution("not_found", source=None, section=section,
                              note=f"{label} was not found in {src.title}.")
        return Resolution("found", source=src, section=section)

    # Cases: 1. exact key
    if key:
        src = repo.find_source_by_key(key)
        if src:
            return Resolution("found", source=src)

    # 2. case name
    if case_name:
        src, score = _match_name(repo, case_name)
        if src and score >= NAME_FOUND:
            if key:   # the case exists, but not at the citation given
                shown = ", ".join(src.citations) or "a different citation"
                return Resolution("found", source=src, mismatch=True,
                                  note=f"The case name matches {src.title}, but the citation given was not "
                                       f"found; the source database lists {shown}.")
            return Resolution("found", source=src)
        if src and score >= NAME_AMBIGUOUS:
            return Resolution("ambiguous", source=None, note=f"Did you mean {src.title}?")

    # 3. not found
    return Resolution("not_found")
