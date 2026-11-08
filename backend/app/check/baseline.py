"""The "ask the LLM to check itself" baseline. Used only by the evaluation for comparison."""
from pathlib import Path

from app.check.types import ChunkInfo
from app.clients.sarvam_llm import LLMJSONError

PROMPT = (Path(__file__).resolve().parent.parent / "prompts" / "baseline_judge.md").read_text(encoding="utf-8")
LABELS = {"supported", "contradicted", "not_enough_info"}


def _user(claim: str, passages: list[ChunkInfo]) -> str:
    body = "\n\n".join(f"[p{i + 1}] {p.source_title}, para {p.para or '-'}:\n{p.text[:2400]}"
                       for i, p in enumerate(passages)) or "(no passages)"
    return f"CLAIM: {claim}\n\nPASSAGES:\n{body}"


async def baseline_judge(llm, claim: str, passages: list[ChunkInfo]) -> tuple[str, float, int]:
    """Returns (label, self-reported confidence, tokens)."""
    try:
        data, tokens = await llm.chat_json(PROMPT, _user(claim, passages), max_tokens=300)
    except LLMJSONError:
        return "not_enough_info", 0.5, 0
    label = str(data.get("label", "not_enough_info")).strip().lower()
    if label not in LABELS:
        label = "not_enough_info"
    try:
        conf = min(1.0, max(0.0, float(data.get("confidence", 0.5))))
    except (TypeError, ValueError):
        conf = 0.5
    return label, conf, tokens
