"""Step 8: suggested corrections. Only exact quote text and citations are ever replaced;
legal propositions are never rewritten automatically."""
from app.check.types import ChunkInfo, ClaimWork, SourceInfo


def citation_for(src: SourceInfo, chunk: ChunkInfo | None) -> str:
    if src.doc_type in ("statute", "rules") and chunk is not None and chunk.para:
        kind = "Article" if "constitution" in src.title.lower() else "Section"
        return f"{kind} {chunk.para} of the {src.title.removeprefix('The ').strip()}"
    return src.citations[0] if src.citations else src.title


def _replace_citation(c: ClaimWork, src: SourceInfo, chunk: ChunkInfo | None, why: str) -> dict:
    return {"kind": "replace_citation", "source_id": src.id, "source_title": src.title,
            "citation": citation_for(src, chunk), "from": c.citation_raw, "chunk_id": chunk.id if chunk else None,
            "note": why}


def suggest_fix(c: ClaimWork) -> dict | None:
    alt = c.alternative
    if c.verdict == "misquote" or (c.verdict == "weak" and c.quote and c.quote.has_diff):
        if c.quote and c.quote.match:
            return {"kind": "replace_quote", "text": c.quote.match, "from": c.quote_text,
                    "chunk_id": c.quote.chunk_id}
    if c.verdict == "fabricated":
        if alt and c.citation_raw:
            src, chunk, p = alt
            return _replace_citation(c, src, chunk, f"{src.title} supports this claim (p={p:.2f}).")
        return {"kind": "remove_claim"}
    if c.resolution.mismatch and c.source and c.citation_raw:
        return _replace_citation(c, c.source, None, "The case exists under a different citation.")
    if alt and c.citation_raw and c.verdict in ("contradicted", "weak", "insufficient"):
        src, chunk, p = alt
        return _replace_citation(c, src, chunk,
                                 f"Not supported by the authority cited, but supported by {src.title} (p={p:.2f}).")
    if c.verdict == "contradicted" and c.evidence:
        return {"kind": "show_source", "chunk_id": c.evidence.id}
    if c.verdict in ("weak", "insufficient"):
        return {"kind": "add_authority"}
    return None
