"""Deterministic citation finder for common Indian formats, each producing a canonical key."""
import re

from app.check.normalize import normalize_chars
from app.check.types import Citation

_AIR = re.compile(r"\bAIR\s*(\d{4})\s+([A-Z][A-Za-z&]*)\s+(\d+)\b")
_SCC = re.compile(r"\((\d{4})\)\s*(\d+)\s*SCC\s*(\d+)\b")
_SCR = re.compile(r"\[(\d{4})\]\s*(?:Supp\.?\s*)?(\d+)\s*SCR\s*(\d+)\b")
_INSC = re.compile(r"\b(\d{4})\s+INSC\s+(\d+)\b")
_ACT = re.compile(
    r"\b[Ss](?:ection|ec\.|\.)\s*(\d+[A-Z]?)((?:\s*\(\w+\))*)\s+of\s+the\s+"
    r"([A-Z][A-Za-z ,()]+?Act)(?:,?\s*(\d{4}))?"
)
_CONST = re.compile(r"\bArt(?:icle|\.)\s*(\d+[A-Z]?)\b")

# Hindi statute citations. The key uses the English act name, so lookup (corpus / Indian Kanoon)
# works the same as for an English draft. No \b here: Devanagari vowel signs are not \w in Python.
_HI_ACTS = {
    r"भारतीय\s+संविदा\s+अधिनियम": "Indian Contract Act",
    r"(?:माध्यस्थम्?|मध्यस्थता)\s+(?:और|एवं|तथा)\s+सुलह\s+अधिनियम": "Arbitration and Conciliation Act",
    r"परक्राम्य\s+लिखत\s+अधिनियम": "Negotiable Instruments Act",
    r"विनिर्दिष्ट\s+अनुतोष\s+अधिनियम": "Specific Relief Act",
    r"परिसीमा\s+अधिनियम": "Limitation Act",
    r"सूचना\s+प्रौद्योगिकी\s+अधिनियम": "Information Technology Act",
}
_HI_ACT = "|".join(f"(?:{p})" for p in _HI_ACTS)
_HI_SEC = r"(\d+[A-Z]?)(?:\s*\(\w+\))*"
# "भारतीय संविदा अधिनियम, 1872 की धारा 73"
_HI_ACT_FIRST = re.compile(rf"({_HI_ACT})(?:\s*,?\s*(\d{{4}}))?\s+(?:की|के)\s+धारा\s+{_HI_SEC}")
# "धारा 73, भारतीय संविदा अधिनियम, 1872"
_HI_SEC_FIRST = re.compile(rf"धारा\s+{_HI_SEC}\s*,?\s*({_HI_ACT})(?:\s*,?\s*(\d{{4}}))?")
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def _hi_act_english(name: str) -> str:
    return next(en for p, en in _HI_ACTS.items() if re.fullmatch(p, name))


def act_name_key(name: str) -> str:
    name = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    name = re.sub(r"^\s*the\s+", "", name)
    return re.sub(r"\s+", " ", name).strip()


def find_citations(text: str) -> list[Citation]:
    t = normalize_chars(text).translate(_DEVANAGARI_DIGITS)   # both 1:1, offsets stay valid
    out: list[Citation] = []
    for m in _AIR.finditer(t):
        y, court, page = m.groups()
        out.append(Citation(text[m.start():m.end()], f"AIR|{y}|{court.upper()}|{page}", "AIR", m.start(), m.end()))
    for m in _SCC.finditer(t):
        y, vol, page = m.groups()
        out.append(Citation(text[m.start():m.end()], f"SCC|{y}|{vol}|{page}", "SCC", m.start(), m.end()))
    for m in _SCR.finditer(t):
        y, vol, page = m.groups()
        out.append(Citation(text[m.start():m.end()], f"SCR|{y}|{vol}|{page}", "SCR", m.start(), m.end()))
    for m in _INSC.finditer(t):
        y, num = m.groups()
        out.append(Citation(text[m.start():m.end()], f"INSC|{y}|{num}", "INSC", m.start(), m.end()))
    for m in _ACT.finditer(t):
        sec, _sub, act, year = m.groups()
        key = f"ACT|{act_name_key(act)}|{year or ''}|S|{sec.upper()}"
        out.append(Citation(text[m.start():m.end()], key, "ACT", m.start(), m.end()))
    for m in _HI_ACT_FIRST.finditer(t):
        act, year, sec = m.groups()
        key = f"ACT|{act_name_key(_hi_act_english(act))}|{year or ''}|S|{sec.upper()}"
        out.append(Citation(text[m.start():m.end()], key, "ACT", m.start(), m.end()))
    for m in _HI_SEC_FIRST.finditer(t):
        sec, act, year = m.groups()
        key = f"ACT|{act_name_key(_hi_act_english(act))}|{year or ''}|S|{sec.upper()}"
        out.append(Citation(text[m.start():m.end()], key, "ACT", m.start(), m.end()))
    for m in _CONST.finditer(t):
        out.append(Citation(text[m.start():m.end()], f"CONST|ART|{m.group(1).upper()}", "CONST", m.start(), m.end()))
    out.sort(key=lambda c: c.char_start)
    return out


def citation_key(raw: str) -> str | None:
    """Canonical key of the first citation in `raw`, or None."""
    found = find_citations(raw)
    return found[0].key if found else None


def parse_act_key(key: str) -> tuple[str, str, str] | None:
    """'ACT|negotiable instruments act|1881|S|138' -> (name, year, section)."""
    parts = key.split("|")
    if len(parts) == 5 and parts[0] == "ACT":
        return parts[1], parts[2], parts[4]
    return None
