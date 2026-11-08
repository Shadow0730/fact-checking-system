"""Build a synthetic labelled claim set from real passages in the corpus (Section 14).

    uv run python scripts/make_eval_set.py --out ../eval/gold --n 300 --dev 100

Variants: true paraphrase, exact quote, fabricated citation, misquote, contradiction,
wrong citation, out of corpus. Uses the Sarvam LLM for paraphrases and contradictions;
in OFFLINE_MODE it falls back to rule-based rewrites.

Every row has "checked": false. Have someone with legal knowledge spot-check at least 50
rows, fix wrong labels and set "checked": true. Report that in the pitch.
"""
import argparse
import asyncio
import json
import random
import re
from pathlib import Path

import _bootstrap  # noqa: F401
import httpx

from app.check.citations import citation_key
from app.check.types import ChunkInfo, SourceInfo
from app.clients import make_clients
from app.config import settings
from app.ingest.pipeline import build_memory_repo

_SENT = re.compile(r"(?<=[.;])\s+(?=[A-Z])")
_PARA = re.compile(r"^\s*\d{1,4}[A-Z]?\.\s+(?:[A-Z][a-z ,]+\.\s+)?")

OUT_OF_CORPUS = [
    "A tenant may be evicted without notice if the rent is unpaid for one month.",
    "A consumer complaint must be filed within two years of the cause of action.",
    "An arbitration clause in an unstamped agreement is unenforceable until the stamp duty is paid.",
    "Anticipatory bail cannot be granted for economic offences.",
    "A will must be registered to be valid.",
    "A trademark registration is valid for ten years and may be renewed.",
    "The limitation period for a money suit is three years from the date the debt became due.",
    "A contract with a minor is void from the beginning.",
    "An employer must pay gratuity to an employee who has completed five years of continuous service.",
    "Specific performance of a contract for personal services cannot be ordered.",
    "A public servant may not be prosecuted without prior sanction.",
    "Copyright in a literary work lasts for the life of the author plus sixty years.",
    "A partnership firm may sue in its own name only if it is registered.",
    "A landlord must return the security deposit within one month of the tenant vacating.",
    "An FIR must be registered when the information discloses a cognizable offence.",
]

SWAPS = [("shall", "may"), ("may", "shall"), ("must", "may"), ("is not", "is"), ("are not", "are"),
         ("not ", ""), ("thirty", "sixty"), ("fifteen", "thirty"), ("one month", "two months"),
         ("two years", "three years"), ("twenty", "forty"), ("three months", "six months"),
         ("only", "also"), ("every", "no"), ("valid", "invalid"), ("rebuttable", "conclusive")]
NEGATE = [(" is ", " is not "), (" shall ", " shall not "), (" may ", " may not "), (" does ", " does not "),
          (" can ", " cannot "), (" must ", " need not "), (" is not ", " is "), (" not ", " ")]


def sentences_of(chunk: ChunkInfo) -> list[str]:
    out = []
    for s in _SENT.split(_PARA.sub("", chunk.text)):
        s = s.strip()
        if 50 <= len(s) <= 300 and len(s.split()) >= 8 and not s.isupper() and "FICTIONAL" not in s:
            out.append(s)
    return out


def mutate(s: str, table, rng: random.Random) -> str | None:
    options = [(a, b) for a, b in table if re.search(rf"\b{re.escape(a.strip())}\b", s, re.I) and a in f" {s} "]
    if not options:
        return None
    a, b = rng.choice(options)
    out = f" {s} ".replace(a, b, 1).strip()
    return out if out != s else None


def fake_scc(rng: random.Random, taken: set[str]) -> str:
    while True:
        c = f"({rng.randint(1995, 2023)}) {rng.randint(1, 12)} SCC {rng.randint(1, 999)}"
        if citation_key(c) not in taken:
            return c


def cite_for(src: SourceInfo, chunk: ChunkInfo) -> str:
    if src.doc_type in ("statute", "rules"):
        return f"Section {chunk.para} of the {src.title.removeprefix('The ')}"
    return src.citations[0] if src.citations else src.title


class Rewriter:
    def __init__(self, llm):
        self.llm = llm

    async def _ask(self, instruction: str, s: str) -> str | None:
        if settings.offline_mode:
            return None
        data, _ = await self.llm.chat_json(
            'You rewrite single sentences from Indian legal sources. Reply with JSON {"text": "..."} only.',
            f"{instruction}\n\nSENTENCE: {s}", max_tokens=400)
        t = str(data.get("text", "")).strip()
        return t or None

    async def paraphrase(self, s: str) -> str:
        t = await self._ask("Paraphrase this sentence faithfully. Keep the legal meaning exactly the same. "
                            "Do not add or remove conditions.", s)
        return t or s

    async def contradict(self, s: str, rng: random.Random) -> str | None:
        t = await self._ask("Rewrite this sentence so that it states the OPPOSITE or a materially different "
                            "legal rule, in a plausible legal style. Change the rule itself, not just the wording.", s)
        return t or mutate(s, NEGATE, rng)


async def build(n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    repo = build_memory_repo(settings.corpus_path)
    sources = {s.id: s for s in repo.sources()}
    if not sources:
        raise SystemExit("No enabled sources with files in the manifest.")
    taken = {k for s in sources.values() for k in s.citation_keys}
    pool = [(sources[c.source_id], c, s) for sid in sources for c in repo.chunks_of(sid)
            if c.para for s in sentences_of(c)]
    if not pool:
        raise SystemExit("No usable sentences found in the corpus.")
    judgments = [s for s in sources.values() if s.doc_type == "judgment"]

    async with httpx.AsyncClient() as http:
        llm, _ = make_clients(http)
        rw = Rewriter(llm)
        variants = ["paraphrase", "quote", "fabricated", "misquote", "contradicted", "wrong_citation", "out"]
        weights = [0.2, 0.15, 0.15, 0.15, 0.15, 0.1, 0.1]
        rows, seen, attempts = [], set(), 0
        while len(rows) < n and attempts < n * 20:
            attempts += 1
            v = rng.choices(variants, weights)[0]
            src, chunk, sent = rng.choice(pool)
            cite = cite_for(src, chunk)
            row = {"claim": None, "citation": cite, "quote": None, "label": "supported", "error_type": None,
                   "source_id": src.id, "para": chunk.para, "variant": v, "checked": False}
            if v == "paraphrase":
                row["claim"] = await rw.paraphrase(sent)
            elif v == "quote":
                row["claim"], row["quote"] = f'The authority states that "{sent}"', sent
            elif v == "fabricated":
                row.update(claim=await rw.paraphrase(sent), citation=fake_scc(rng, taken),
                           label="bad", error_type="fabricated_citation", source_id=None, para=None)
            elif v == "misquote":
                m = mutate(sent, SWAPS, rng)
                if not m:
                    continue
                row.update(claim=f'The authority states that "{m}"', quote=m, label="bad", error_type="misquote")
            elif v == "contradicted":
                m = await rw.contradict(sent, rng)
                if not m:
                    continue
                row.update(claim=m, label="bad", error_type="contradicted")
            elif v == "wrong_citation":
                if src.doc_type == "judgment":
                    others = [j for j in judgments if j.id != src.id]
                    if not others:
                        continue
                    other = rng.choice(others)
                    wrong = other.citations[0] if other.citations else other.title
                else:
                    secs = [c.para for c in repo.chunks_of(src.id) if c.para and c.para != chunk.para]
                    if not secs:
                        continue
                    wrong = f"Section {rng.choice(secs)} of the {src.title.removeprefix('The ')}"
                row.update(claim=await rw.paraphrase(sent), citation=wrong, label="bad", error_type="wrong_citation")
            else:
                row.update(claim=rng.choice(OUT_OF_CORPUS), citation=None, label="not_enough_info",
                           source_id=None, para=None)
            sig = (row["claim"], row["citation"], row["quote"])
            if sig in seen and v != "out":
                continue
            seen.add(sig)
            rows.append(row)
    rng.shuffle(rows)
    for i, r in enumerate(rows):
        r["id"] = f"g-{i + 1:04d}"
    return [{"id": r.pop("id"), **r} for r in rows]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="../eval/gold")
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--dev", type=int, default=100)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rows = asyncio.run(build(args.n, args.seed))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, part in (("dev", rows[: args.dev]), ("test", rows[args.dev:])):
        with (out / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for r in part:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"wrote {len(part)} rows to {out / (name + '.jsonl')}")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["variant"]] = counts.get(r["variant"], 0) + 1
    print("variants:", counts)
    if settings.offline_mode:
        print("NOTE: OFFLINE_MODE rewrites are rule-based (paraphrases are verbatim). Regenerate with a key.")


if __name__ == "__main__":
    main()
