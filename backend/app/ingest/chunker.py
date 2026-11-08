"""Split a document into chunks on numbered paragraphs (judgments) or section headings
(statutes), keeping page and paragraph numbers. Text stays verbatim apart from whitespace."""
import bisect
import re
import unicodedata
from dataclasses import dataclass

from app.check.normalize import normalize_chars

_JUDG_PARA = re.compile(r"^[ \t]*(\d{1,3})\.[ \t]+(?=\S)", re.M)
_STAT_SEC = re.compile(r"^[ \t]*(?:Section|Sec\.|Article|Art\.)?[ \t]*(\d{1,4}[A-Z]{0,2})\.[ \t]+(?=\S)", re.M)
_HYPHEN_BREAK = re.compile(r"([^\W\d_])-[ \t]*\r?\n[ \t]*(?=[a-z])")
_SENT_END = re.compile(r"(?<=[.;:])\s+(?=[A-Z(\"'])")


@dataclass
class RawChunk:
    ord: int
    text: str
    para: str | None
    page_start: int
    page_end: int


def _clean_page(t: str) -> str:
    t = normalize_chars(unicodedata.normalize("NFKC", t))
    t = _HYPHEN_BREAK.sub(r"\1", t)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n{3,}", "\n\n", t)


def _num(s: str) -> tuple[int, str]:
    m = re.match(r"(\d+)([A-Z]*)", s)
    return (int(m.group(1)), m.group(2)) if m else (0, "")


def _markers(text: str, sectioning: str) -> list[tuple[int, str]]:
    """(offset, number) for each accepted paragraph/section start."""
    out: list[tuple[int, str]] = []
    if sectioning == "statute":
        last = (0, "")
        for m in _STAT_SEC.finditer(text):
            n = _num(m.group(1))
            if n > last:                 # sections only go forwards (138 < 138A < 139)
                out.append((m.start(), m.group(1)))
                last = n
    else:
        last = 0
        for m in _JUDG_PARA.finditer(text):
            n = int(m.group(1))
            if n == last + 1 or (not out and n <= 2):   # numbered paras run 1, 2, 3, ...
                out.append((m.start(), m.group(1)))
                last = n
    return out


def _split_long(text: str, target: int, hard_max: int) -> list[str]:
    if len(text) <= hard_max:
        return [text]
    pieces, cur = [], ""
    for sent in _SENT_END.split(text):
        if cur and len(cur) + len(sent) + 1 > target:
            pieces.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}" if cur else sent
        while len(cur) > hard_max:                # a single enormous "sentence"
            pieces.append(cur[:target])
            cur = cur[target:]
    if cur:
        pieces.append(cur)
    return pieces


def chunk_document(pages: list[tuple[int, str]], sectioning: str = "judgment",
                   target_chars: int = 1800, max_chars: int = 3000) -> list[RawChunk]:
    starts, parts, nums, pos = [], [], [], 0
    for num, t in pages:
        t = _clean_page(t)
        starts.append(pos)
        nums.append(num)
        parts.append(t)
        pos += len(t) + 1
    full = "\n".join(parts)

    def page_at(off: int) -> int:
        return nums[max(0, bisect.bisect_right(starts, off) - 1)] if nums else 1

    marks = _markers(full, sectioning)
    segments: list[tuple[int, int, str | None]] = []
    if not marks:
        segments.append((0, len(full), None))
    else:
        if full[: marks[0][0]].strip():
            segments.append((0, marks[0][0], None))
        for i, (off, para) in enumerate(marks):
            end = marks[i + 1][0] if i + 1 < len(marks) else len(full)
            segments.append((off, end, para))

    chunks: list[RawChunk] = []
    for s, e, para in segments:
        seg = full[s:e]
        if not seg.strip():
            continue
        # Without markers, split by size; with markers, only split paragraphs that are too long.
        limit = max_chars if para is not None else target_chars
        cursor = s
        for piece in _split_long(" ".join(seg.split()), target_chars, limit):
            text = piece.strip()
            if not text:
                continue
            chunks.append(RawChunk(len(chunks), text, para, page_at(cursor), page_at(min(e - 1, cursor + len(piece)))))
            cursor += len(piece)
    return chunks
