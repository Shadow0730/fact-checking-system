"""Find quoted passages in a draft and verify them against source text (rapidfuzz, no AI)."""
import difflib
import re
from collections.abc import Sequence

from rapidfuzz import fuzz

from app.check.normalize import norm_with_map, normalize_chars
from app.check.types import ChunkInfo, Quote, QuoteResult

MIN_QUOTE_WORDS = 6
CRITICAL_WORDS = {"shall", "may", "must", "not", "no", "never", "only", "except", "unless",
                  "cannot", "nor", "without", "mandatory", "discretionary"}

_QUOTED = re.compile(r'"([^"]{3,4000}?)"', re.S)
_BLOCK = re.compile(r"^(?:[ \t]{4,}|\t)(\S.*)$", re.M)


def _words(s: str) -> int:
    return len(s.split())


# Below this match score the draft's quote and the best passage are different texts, not a misquote of it.
QUOTE_RELATED = 70


def find_quotes(text: str) -> list[Quote]:
    t = normalize_chars(text)
    quotes: list[Quote] = []
    for m in _QUOTED.finditer(t):
        inner = m.group(1)
        if _words(inner) >= MIN_QUOTE_WORDS:
            quotes.append(Quote(text[m.start(1):m.end(1)].strip(), m.start(1), m.end(1)))
    for m in _BLOCK.finditer(t):
        s, e = m.start(1), m.end(1)
        if _words(m.group(1)) >= MIN_QUOTE_WORDS and not any(q.char_start <= s < q.char_end for q in quotes):
            quotes.append(Quote(text[s:e].strip().strip('"'), s, e))
    quotes.sort(key=lambda q: q.char_start)
    return quotes


def _is_critical(words: Sequence[str]) -> bool:
    return any(w in CRITICAL_WORDS or any(ch.isdigit() for ch in w) for w in words)


def _word_spans(s: str, start: int, end: int) -> list[tuple[int, int]]:
    return [(start + m.start(), start + m.end()) for m in re.finditer(r"\S+", s[start:end])]


def verify_quote(quote: str, chunks: Sequence[ChunkInfo]) -> QuoteResult:
    """Best fuzzy alignment of `quote` inside any chunk (or two consecutive chunks)."""
    q, _ = norm_with_map(quote)
    empty = QuoteResult(0.0, "", None, [], False, True)
    if not q:
        return empty

    candidates: list[tuple[int, str]] = [(c.id, c.text) for c in chunks]
    ordered = sorted(chunks, key=lambda c: (c.source_id, c.ord))
    for a, b in zip(ordered, ordered[1:]):
        if a.source_id == b.source_id and b.ord == a.ord + 1:
            candidates.append((a.id, a.text + "\n" + b.text))   # quotes spanning a chunk boundary

    best_score, best = -1.0, None
    for cid, ctext in candidates:
        t, tmap = norm_with_map(ctext)
        if not t or len(q) > len(t):
            continue
        al = fuzz.partial_ratio_alignment(q, t)
        if al is not None and al.score > best_score:
            best_score, best = al.score, (cid, ctext, t, tmap, al)
            if al.score == 100:
                break
    if best is None:
        return empty

    cid, ctext, t, tmap, al = best
    s, e = al.dest_start, al.dest_end
    while s > 0 and t[s - 1] != " ":          # snap to whole words
        s -= 1
    while e < len(t) and t[e] != " ":
        e += 1
    spans = _word_spans(t, s, e)
    src_words = [t[a:b] for a, b in spans]
    q_words = q.split()

    ops = difflib.SequenceMatcher(None, q_words, src_words, autojunk=False).get_opcodes()
    # Trim extra source words picked up at the edges of the window.
    if ops and ops[0][0] == "insert":
        spans = spans[ops[0][4]:]
        src_words = src_words[ops[0][4]:]
    if ops and ops[-1][0] == "insert" and len(ops) > 1:
        cut = ops[-1][4] - ops[-1][3]
        spans, src_words = spans[: len(spans) - cut], src_words[: len(src_words) - cut]
    ops = difflib.SequenceMatcher(None, q_words, src_words, autojunk=False).get_opcodes()

    diff: list[dict] = []
    critical = False
    for tag, i1, i2, j1, j2 in ops:
        d, src = q_words[i1:i2], src_words[j1:j2]
        diff.append({"op": tag, "draft": " ".join(d), "source": " ".join(src)})
        if tag != "equal" and (_is_critical(d) or _is_critical(src)):
            critical = True
    has_diff = any(op["op"] != "equal" for op in diff)

    if spans:
        o_start, o_end = tmap[spans[0][0]], tmap[spans[-1][1] - 1] + 1
        match = ctext[o_start:o_end]
    else:
        match = ""
    score = float(al.score)
    if has_diff and score >= 100:
        score = 99.0
    # A "meaning-changing word" only means something when the texts are clearly the same passage.
    critical = critical and score >= QUOTE_RELATED
    return QuoteResult(round(score, 1), " ".join(match.split()), cid, diff, critical, has_diff)


def quote_is_exact(r: QuoteResult | None, exact: float) -> bool:
    return r is not None and r.score >= exact and not r.has_diff
