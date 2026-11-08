"""Text normalisation shared by quotes and citations, so the two always agree.

Three levels:
- normalize_chars: 1:1 character mapping (curly quotes, dashes, nbsp). Keeps offsets valid.
- clean:          display/ingest form. NFKC, de-hyphenate line ends, collapse whitespace.
- norm_with_map:  matching form (lower-case, punctuation stripped) PLUS a map back to the
                  original string's indices, so a match can be shown in the original words.
"""
import re
import unicodedata

_CHAR_MAP = str.maketrans({
    "“": '"', "”": '"', "„": '"', "‟": '"', "«": '"', "»": '"',
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "–": "-", "—": "-", "‒": "-", "−": "-", "­": "-",
    " ": " ", " ": " ", " ": " ", " ": " ",
})

_HYPHEN_BREAK = re.compile(r"([^\W\d_])-[ \t]*\r?\n\s*(?=[a-z])")
_WS = re.compile(r"\s+")
_HYPHEN_AT = re.compile(r"-[ \t]*\r?\n\s*(?=[a-z])")


def normalize_chars(text: str) -> str:
    """Same length as the input; safe to use before computing character offsets."""
    return text.translate(_CHAR_MAP)


def clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = normalize_chars(text)
    text = _HYPHEN_BREAK.sub(r"\1", text)
    return _WS.sub(" ", text).strip()


def _keep(ch: str) -> bool:
    if ch == "§":
        return True
    cat = unicodedata.category(ch)
    return cat[0] in ("L", "N", "M")   # letters, digits, and combining marks (Indic vowel signs)


def norm_with_map(text: str) -> tuple[str, list[int]]:
    """Matching form + index map: norm[i] came from text[idx[i]]."""
    t = normalize_chars(text)
    out: list[str] = []
    idx: list[int] = []
    prev_space = True
    i, n = 0, len(t)
    while i < n:
        ch = t[i]
        if ch == "-" and out and out[-1].isalpha():
            m = _HYPHEN_AT.match(t, i)
            if m:                      # "judg-\nment" -> "judgment"
                i = m.end()
                continue
        if _keep(ch):
            low = ch.lower()
            out.append(low if len(low) == 1 else ch)
            idx.append(i)
            prev_space = False
        elif not prev_space:
            out.append(" ")
            idx.append(i)
            prev_space = True
        i += 1
    if out and out[-1] == " ":
        out.pop()
        idx.pop()
    return "".join(out), idx


def norm_for_match(text: str) -> str:
    return norm_with_map(text)[0]


def norm_name(text: str) -> str:
    """For case/act names: lower-case, unify 'vs'/'versus' to 'v', drop punctuation."""
    s = norm_for_match(text)
    s = re.sub(r"\b(vs|versus)\b", "v", s)
    return _WS.sub(" ", s).strip()
