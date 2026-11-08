"""PDF (PyMuPDF), DOCX (python-docx), TXT -> list of (page_number, text)."""
import io
from pathlib import Path

SUPPORTED = {".pdf", ".docx", ".txt", ".md"}


class UnsupportedFile(ValueError):
    pass


def load_bytes(data: bytes, suffix: str) -> list[tuple[int, str]]:
    suffix = suffix.lower()
    if suffix == ".pdf":
        import fitz  # PyMuPDF

        with fitz.open(stream=data, filetype="pdf") as doc:
            return [(i + 1, page.get_text("text")) for i, page in enumerate(doc)]
    if suffix == ".docx":
        import docx

        d = docx.Document(io.BytesIO(data))
        return [(1, "\n".join(p.text for p in d.paragraphs))]
    if suffix in (".txt", ".md"):
        text = data.decode("utf-8-sig", errors="replace")
        pages = text.split("\f")        # form feed = page break in plain-text exports
        return [(i + 1, p) for i, p in enumerate(pages)]
    raise UnsupportedFile(f"Unsupported file type {suffix!r}; use .pdf, .docx or .txt")


def load_file(path: Path) -> list[tuple[int, str]]:
    return load_bytes(path.read_bytes(), path.suffix)


def load_text(data: bytes, filename: str) -> str:
    """Whole document as one string (for drafts uploaded to /api/checks)."""
    return "\n".join(t for _, t in load_bytes(data, Path(filename).suffix))
