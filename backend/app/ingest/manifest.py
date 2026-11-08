"""Loads and validates corpus/manifest.yaml."""
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError


class ManifestEntry(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9\-_]{1,80}$")
    title: str
    doc_type: Literal["judgment", "statute", "rules", "circular"]
    court: str | None = None
    year: int | None = None
    language: str = "en"
    citations: list[str] = []
    aliases: list[str] = []
    file: str
    sectioning: Literal["judgment", "statute"] | None = None
    enabled: bool = True

    @property
    def effective_sectioning(self) -> str:
        if self.sectioning:
            return self.sectioning
        return "statute" if self.doc_type in ("statute", "rules") else "judgment"


class Manifest(BaseModel):
    sources: list[ManifestEntry]


def load_manifest(corpus_dir: Path) -> list[ManifestEntry]:
    path = corpus_dir / "manifest.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No manifest at {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    try:
        m = Manifest.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"Invalid {path}:\n{e}") from e
    ids = [s.id for s in m.sources]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"Duplicate source ids in manifest: {sorted(dupes)}")
    return m.sources


def append_entry(corpus_dir: Path, entry: ManifestEntry) -> None:
    """Used by the upload endpoint so CLI re-ingestion keeps uploaded sources."""
    path = corpus_dir / "manifest.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
    data = data or {"sources": []}
    data["sources"] = [s for s in data.get("sources", []) if s.get("id") != entry.id]
    data["sources"].append(entry.model_dump(exclude_none=True))
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
