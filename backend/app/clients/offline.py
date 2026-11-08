"""Fake LLM/Prism used when OFFLINE_MODE=true. For UI development only: results are NOT meaningful.

OfflinePrism reads the same `state` the real Prism gets and answers from keyword overlap
plus a crude negation / shall-may check, so the whole pipeline runs end to end without a key.
"""
import re

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = set("""a an the of to in on at by for from with and or but is are was were be been being as that this
these those it its which who whom whose such any all there their than then so if into upon also said same
court held hold holds observed""".split())
_NEG = {"not", "no", "never", "cannot", "nor", "without"}
_MODAL = {"shall", "may", "must"}


def _stem(w: str) -> str:
    for suf in ("ings", "ing", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _terms(text: str) -> set[str]:
    return {_stem(w) for w in _TOKEN.findall(text.lower()) if w not in _STOP and w not in _NEG}


def _raw(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


_HELD = re.compile(r"\b(?:held|holds|observed|ruled|provides|says)\s+(?:that\s+)?", re.I)
_UNDER = re.compile(r"^\s*(?:Under|As per|In terms of)\s+[^,]{3,120},\s*", re.I)
_CLAUSE = re.compile(r",\s+(?:and|but)\s+|;\s+")
_SENT_SPLIT = re.compile(r"(?<=[.;:])\s+|\s+(?=\(\d+\)\s)")


def _proposition(claim: str) -> str:
    """Drop the 'In X v. Y, (cite), the Court held that' / 'Under Section N of the Act,' framing."""
    m = _HELD.search(claim)
    if m:
        return claim[m.end():]
    return _UNDER.sub("", claim)


def _best_sentence(terms: set[str], passages: list[str]) -> tuple[float, int, str]:
    best = (0.0, 0, "")
    for pi, p in enumerate(passages):
        for sent in _SENT_SPLIT.split(p):
            cov = len(terms & _terms(sent)) / len(terms)
            if cov > best[0] + 1e-9:
                best = (cov, pi, sent)
    return best


def _anchored_negation(text: str, other_terms: set[str]) -> bool:
    """A negation counts only if one of the next 3 words is a term the other text shares
    ("is not liable" vs "is liable"); "No court shall ..." about something else does not."""
    words = _TOKEN.findall(text.lower())
    for i, w in enumerate(words):
        if w in _NEG and any(_stem(x) in other_terms for x in words[i + 1:i + 4]):
            return True
    return False


def _clash(a: str, b: str) -> bool:
    if _anchored_negation(a, _terms(b)) != _anchored_negation(b, _terms(a)):
        return True
    a_raw, b_raw = _raw(a), _raw(b)
    am, bm = a_raw & _MODAL, b_raw & _MODAL
    return len(am) == 1 and len(bm) == 1 and am != bm


def overlap_judgement(claim: str, passages: list[str], cited: str = "") -> tuple[dict[str, float], int]:
    """(probabilities, index of best passage)."""
    prop = _proposition(claim)
    c_terms = _terms(prop) - _terms(cited)
    if not c_terms or not passages:
        return {"supported": 0.02, "contradicted": 0.02, "not_enough_info": 0.96}, 0
    cov, pi, _ = _best_sentence(c_terms, passages)
    contradicted = False
    for clause in _CLAUSE.split(prop):           # a clash inside any well-matched clause
        ct = _terms(clause) - _terms(cited)
        if len(ct) < 3:
            continue
        ccov, _, csent = _best_sentence(ct, passages)
        if ccov >= 0.6 and _clash(clause, csent):
            contradicted = True
            break
    if contradicted:
        probs = {"supported": 0.12, "contradicted": 0.76, "not_enough_info": 0.12}
    else:
        sup = max(0.02, min(0.97, (cov - 0.25) / 0.55))
        con = 0.02
        probs = {"supported": round(sup, 3), "contradicted": con,
                 "not_enough_info": round(max(0.01, 1 - sup - con), 3)}
    total = sum(probs.values())
    return {k: v / total for k, v in probs.items()}, pi


class OfflinePrism:
    async def decide(self, state: dict | str, questions: dict) -> tuple[dict, int]:
        st = state if isinstance(state, dict) else {"claim": str(state), "passages": []}
        claim = st.get("claim", "")
        passages = [p.get("text", "") for p in st.get("passages", [])]
        cited = st.get("cited_authority") or ""
        probs, best = overlap_judgement(claim, passages, "" if cited == "none" else cited)
        answers: dict = {}
        for name, q in questions.items():
            options = list(q.get("criteria", {}))
            if name == "support":
                choice = max(probs, key=probs.get)
                answers[name] = {"type": "choice", "choice": choice, "probabilities": probs}
            else:
                pick = options[best] if best < len(options) else options[0]
                pr = {o: (0.9 if o == pick else 0.1 / max(1, len(options) - 1)) for o in options}
                answers[name] = {"type": "choice", "choice": pick, "probabilities": pr}
        return answers, 0


class OfflineLLM:
    """Only the baseline uses an LLM in offline mode; it mimics an over-confident self-check."""

    async def chat_json(self, system: str, user: str, max_tokens: int | None = None) -> tuple[dict, int]:
        m = re.search(r"CLAIM:\s*(.*?)\n\s*PASSAGES:\s*(.*)", user, re.S)
        if not m:
            return {"label": "not_enough_info", "confidence": 0.9}, 0
        probs, _ = overlap_judgement(m.group(1), [m.group(2)])
        label = max(probs, key=probs.get)
        return {"label": label, "confidence": 0.9}, 0
