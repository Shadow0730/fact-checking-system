"""Step 6: one Prism request per claim, two questions about the same state."""
from app.check.types import ChunkInfo, ClaimWork

LABELS = ("supported", "contradicted", "not_enough_info")
MAX_PASSAGE_CHARS = 2400

SUPPORT_QUESTION = {
    "type": "choice",
    "instructions": (
        "Using ONLY the passages, decide whether they support the claim. "
        "'supported' = the passages state or directly imply the claim. "
        "'contradicted' = the passages state the opposite or a materially different rule. "
        "'not_enough_info' = the passages do not settle it. Do not use outside knowledge."
    ),
    "criteria": {
        "supported": "The passages support the claim",
        "contradicted": "The passages contradict the claim",
        "not_enough_info": "The passages do not settle the claim",
    },
}


def build_request(claim_text: str, cited: str | None, passages: list[ChunkInfo]) -> tuple[dict, dict]:
    state = {
        "claim": claim_text,
        "cited_authority": cited or "none",
        "passages": [
            {"id": f"p{i + 1}", "source": p.source_title, "para": p.para or "",
             "text": p.text[:MAX_PASSAGE_CHARS]}
            for i, p in enumerate(passages)
        ],
    }
    questions: dict = {"support": SUPPORT_QUESTION}
    if len(passages) >= 2:   # a choice needs at least 2 options
        questions["best_passage"] = {
            "type": "choice",
            "instructions": "Which single passage is most relevant to the claim?",
            "criteria": {f"p{i + 1}": " ".join(p.text[:200].split()) for i, p in enumerate(passages)},
        }
    return state, questions


def parse_answers(answers: dict, passages: list[ChunkInfo]) -> tuple[dict[str, float], ChunkInfo | None]:
    raw = (answers.get("support") or {}).get("probabilities") or {}
    probs = {k: float(raw.get(k, 0.0)) for k in LABELS}
    total = sum(probs.values())
    probs = {k: v / total for k, v in probs.items()} if total > 0 else {"supported": 0.0, "contradicted": 0.0,
                                                                         "not_enough_info": 1.0}
    evidence = passages[0] if passages else None
    choice = (answers.get("best_passage") or {}).get("choice")
    if choice and choice.startswith("p") and choice[1:].isdigit():
        i = int(choice[1:]) - 1
        if 0 <= i < len(passages):
            evidence = passages[i]
    return probs, evidence


async def judge_passages(prism, claim_text: str, cited: str | None,
                         passages: list[ChunkInfo]) -> tuple[dict[str, float], ChunkInfo | None, int]:
    if not passages:
        return {"supported": 0.0, "contradicted": 0.0, "not_enough_info": 1.0}, None, 0
    state, questions = build_request(claim_text, cited, passages)
    answers, tokens = await prism.decide(state, questions)
    probs, evidence = parse_answers(answers, passages)
    return probs, evidence, tokens


async def judge(prism, claim: ClaimWork) -> None:
    cited = claim.citation_raw or claim.case_name
    claim.support_probs, claim.evidence, claim.prism_tokens = await judge_passages(
        prism, claim.text, cited, claim.passages)
