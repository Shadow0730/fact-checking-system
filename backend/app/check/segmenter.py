"""Draft -> numbered sentences with character offsets into the ORIGINAL text."""
import re

from app.check.types import Sentence

# Abbreviations that cause false sentence breaks in legal text. Their "." is swapped for a
# one-character placeholder before splitting, which keeps every offset unchanged.
_ABBREV = re.compile(
    r"\b(?:v|vs|Ltd|Pvt|No|Nos|S|Ss|Sec|Art|Arts|para|paras|p|pp|Cl|Ors|Anr|Co|Corp|Inc|Rs|Hon'ble|"
    r"cf|viz|Supp|Vol|Mr|Mrs|Ms|Dr|Smt|Shri|Sh|Govt|Dept|Admn|Spl|Crl|Cri|Civ|Misc|Ch|Sch)\.",
    re.IGNORECASE,
)
_INITIAL = re.compile(r"\b[A-Z]\.(?=\s*[A-Z])")          # "M. K. Gandhi", "S. 138"
_ABBR_DOTS = re.compile(r"\b(?:i\.e|e\.g|etc)\.", re.IGNORECASE)
_LIST_NUM = re.compile(r"^(?:\(?\d{1,3}[.)]|\([a-z]\))\s+")      # "3. ", "(2) ", "(a) "
_PLACEHOLDER = "․"                                 # ONE DOT LEADER, same length as "."

try:
    import pysbd

    _seg = pysbd.Segmenter(language="en", clean=False)
except Exception:  # pragma: no cover - pysbd is a declared dependency
    _seg = None

_FALLBACK = re.compile(r"[^.!?]+(?:[.!?]+[\"')\]]*|$)")


def _protect(text: str) -> str:
    def dots(m: re.Match) -> str:
        return m.group(0).replace(".", _PLACEHOLDER)

    text = _ABBREV.sub(dots, text)
    text = _ABBR_DOTS.sub(dots, text)
    return _INITIAL.sub(dots, text)


_DANDA = re.compile(r"(?<=[।॥])\s*")       # Hindi full stop; pysbd's English model ignores it


def _split(line: str) -> list[str]:
    out: list[str] = []
    for part in _DANDA.split(line):
        if not part.strip():
            continue
        if _seg is not None:
            out += _seg.segment(part)
        else:
            out += [m.group(0) for m in _FALLBACK.finditer(part) if m.group(0).strip()]
    return out


def segment(text: str) -> list[Sentence]:
    """Split each line separately (so headings don't merge with the next sentence),
    then map each sentence back to exact offsets in `text`."""
    protected = _protect(text)
    sentences: list[Sentence] = []
    pos = 0
    for line in protected.splitlines(keepends=True):
        line_start = pos
        pos += len(line)
        if not line.strip():
            continue
        cursor = 0
        for piece in _split(line):
            p = piece.strip()
            if not p:
                continue
            at = line.find(p, cursor)
            if at < 0:              # pysbd altered the text; fall back to the cursor
                at = cursor
            cursor = at + len(p)
            lead = _LIST_NUM.match(p)       # "3. Under Section ..." -> "Under Section ..."
            if lead and lead.end() < len(p):
                at += lead.end()
                p = p[lead.end():]
            elif lead:                       # a bare "3." on its own
                continue
            start = line_start + at
            end = start + len(p)
            sentences.append(Sentence(f"S{len(sentences) + 1}", text[start:end], start, end))
    return sentences
