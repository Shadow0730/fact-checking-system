"""Run the pipeline (and optionally the LLM self-check baseline) on a gold file; write metrics.

    uv run python scripts/run_eval.py --dataset dev  --sweep-thresholds
    uv run python scripts/run_eval.py --dataset test --with-baseline
    uv run python scripts/run_eval.py --dataset test --memory     # no database needed

Results go to eval/results/ and to the eval_runs table (shown on the /eval page).
"""
import argparse
import asyncio
import json
import statistics
import time
from datetime import UTC, datetime

import _bootstrap  # noqa: F401
import httpx

from app.check.baseline import baseline_judge
from app.check.citations import citation_key
from app.check.pipeline import PRISM_INR_PER_TOKEN, Deps, check_claims
from app.check.scorer import Thresholds, score
from app.check.types import ClaimWork
from app.clients import make_clients
from app.config import REPO_DIR, settings
from app.ingest.embedder import get_embedder
from app.logging import setup_logging

GOLD = REPO_DIR / "eval" / "gold"
RESULTS = REPO_DIR / "eval" / "results"
BATCH = 40
# For calibration: which judge labels count as correct for each gold row type.
JUDGE_OK = {"supported": {"supported"}, "contradicted": {"contradicted"},
            "wrong_citation": {"contradicted", "not_enough_info"}, "not_enough_info": {"not_enough_info"}}


def load_gold(dataset: str) -> list[dict]:
    path = GOLD / f"{dataset}.jsonl"
    if not path.exists():
        raise SystemExit(f"{path} not found. Run scripts/make_eval_set.py first.")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def to_claim(i: int, r: dict) -> ClaimWork:
    cite, quote = r.get("citation"), r.get("quote")
    key = citation_key(cite) if cite else None
    kind = key.split("|")[0] if key else None
    ctype = "quote" if quote else ("statutory" if kind in ("ACT", "CONST") else "holding")
    return ClaimWork(ord=i, text=r["claim"], claim_type=ctype, char_start=0, char_end=len(r["claim"]),
                     citation_raw=cite, citation_key=key, citation_kind=kind,
                     case_name=None if key else cite, quote_text=quote)


def gold_kind(r: dict) -> str:
    return r["label"] if r["label"] != "bad" else r["error_type"]


# ── metrics ──────────────────────────────────────────────────────────────────
def calibration(points: list[tuple[float, bool]], bins: int = 10) -> tuple[list[dict], float | None]:
    if not points:
        return [], None
    out, ece, n = [], 0.0, len(points)
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        sel = [(c, ok) for c, ok in points if lo <= c < hi or (b == bins - 1 and c == 1.0)]
        if not sel:
            continue
        mc = sum(c for c, _ in sel) / len(sel)
        acc = sum(ok for _, ok in sel) / len(sel)
        ece += len(sel) / n * abs(mc - acc)
        out.append({"lo": lo, "hi": hi, "n": len(sel), "mean_confidence": round(mc, 4), "accuracy": round(acc, 4)})
    return out, round(ece, 4)


def metrics(items: list[dict]) -> dict:
    flagged = [i["colour"] == "red" or i["verdict"] == "weak" for i in items]
    bad = [i["label"] == "bad" for i in items]
    tp = sum(f and b for f, b in zip(flagged, bad))
    fp = sum(f and not b for f, b in zip(flagged, bad))
    fn = sum(b and not f for f, b in zip(flagged, bad))
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f05 = (1.25 * p * r / (0.25 * p + r)) if (p + r) else 0.0

    catch: dict[str, dict] = {}
    for it, f in zip(items, flagged):
        if it["label"] == "bad":
            d = catch.setdefault(it["error_type"], {"n": 0, "caught": 0, "red": 0})
            d["n"] += 1
            d["caught"] += f
            d["red"] += it["colour"] == "red"
    for d in catch.values():
        d["rate"] = round(d["caught"] / d["n"], 4)

    nei = [i for i in items if i["label"] == "not_enough_info"]
    points = [(i["conf"], i["pred"] in JUDGE_OK[gold_kind(i)]) for i in items
              if gold_kind(i) in JUDGE_OK and i["conf"] is not None]
    bins, ece = calibration(points)

    def auto(t: float) -> dict:
        sel = [i for i in items if i["p_supported"] is not None and i["p_supported"] >= t]
        err = sum(i["label"] != "supported" for i in sel)
        return {"threshold": t, "auto_verified": len(sel), "share": round(len(sel) / len(items), 4) if items else 0,
                "error_rate": round(err / len(sel), 4) if sel else None}

    secs = [i["seconds"] for i in items if i.get("seconds") is not None]
    return {
        "n": len(items), "bad": sum(bad), "flagged": sum(flagged),
        "precision": round(p, 4), "recall": round(r, 4), "f05": round(f05, 4),
        "catch_rate": catch,
        "abstention_rate": round(sum(i["verdict"] == "insufficient" for i in items) / len(items), 4) if items else 0,
        "nei_abstained": round(sum(i["verdict"] == "insufficient" for i in nei) / len(nei), 4) if nei else None,
        "verdicts": {v: sum(i["verdict"] == v for i in items) for v in
                     ("verified", "weak", "insufficient", "misquote", "contradicted", "fabricated")},
        "calibration": bins, "ece": ece,
        "coverage_at_090": auto(0.9),
        "threshold_table": [auto(t) for t in (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)],
        "median_seconds_per_claim": round(statistics.median(secs), 3) if secs else None,
    }


def pipeline_items(rows: list[dict], claims: list[ClaimWork], secs: float) -> list[dict]:
    out = []
    for r, c in zip(rows, claims):
        probs = c.support_probs or {}
        pred = max(probs, key=probs.get) if probs else None
        out.append({"id": r["id"], "label": r["label"], "error_type": r.get("error_type"), "verdict": c.verdict,
                    "colour": c.colour, "pred": pred, "conf": max(probs.values()) if probs else None,
                    "p_supported": probs.get("supported"), "seconds": secs / max(1, len(claims))})
    return out


def baseline_verdict(label: str, conf: float, th: Thresholds) -> tuple[str, str]:
    if label == "contradicted":
        return "contradicted", "red"
    if label == "supported" and conf >= th.supported:
        return "verified", "green"
    if label == "supported" and conf >= th.weak:
        return "weak", "amber"
    return "insufficient", "amber"


def sweep(rows: list[dict], claims: list[ClaimWork], base: Thresholds) -> list[dict]:
    table = []
    for sup in (0.7, 0.75, 0.8, 0.85, 0.9, 0.93, 0.95, 0.97):
        for weak in (0.4, 0.5, 0.6, 0.7):
            if weak >= sup:
                continue
            for con in (0.3, 0.4, 0.5, 0.6, 0.7):
                th = Thresholds(sup, weak, con, base.quote_exact, base.quote_near)
                for c in claims:
                    score(c, th)
                m = metrics(pipeline_items(rows, claims, 0))
                table.append({"supported": sup, "weak": weak, "contradicted": con, "f05": m["f05"],
                              "precision": m["precision"], "recall": m["recall"],
                              "abstention_rate": m["abstention_rate"]})
    for c in claims:
        score(c, base)
    table.sort(key=lambda x: (-x["f05"], x["abstention_rate"]))
    return table


def save(dataset: str, mode: str, config: dict, m: dict, use_db: bool) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    payload = {"dataset": dataset, "mode": mode, "created_at": datetime.now(UTC).isoformat(),
               "config": config, "metrics": m}
    (RESULTS / f"{dataset}-{mode}-{stamp}.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
    latest = RESULTS / f"latest-{dataset}.json"
    combined = json.loads(latest.read_text(encoding="utf-8")) if latest.exists() else {"dataset": dataset}
    combined[mode] = {k: payload[k] for k in ("created_at", "config", "metrics")}
    latest.write_text(json.dumps(combined, indent=1), encoding="utf-8")
    if use_db:
        try:
            from app.db import session_scope
            from app.models import EvalRun

            with session_scope() as s:
                s.add(EvalRun(dataset=dataset, mode=mode, config=config, metrics=m))
        except Exception as e:  # noqa: BLE001 - results are on disk anyway
            print(f"  (could not write eval_runs to the database: {e})")


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default="dev", choices=["dev", "test"])
    ap.add_argument("--with-baseline", action="store_true")
    ap.add_argument("--sweep-thresholds", action="store_true")
    ap.add_argument("--memory", action="store_true", help="load the corpus into memory instead of Postgres")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    setup_logging("WARNING")

    rows = load_gold(args.dataset)
    if args.limit:
        rows = rows[: args.limit]
    th = Thresholds.from_settings()
    embedder = get_embedder()
    session = None
    args.memory = args.memory or not settings.use_db      # no DATABASE_URL -> always in memory
    if args.memory:
        from app.ingest.pipeline import build_memory_repo

        repo = build_memory_repo(settings.corpus_path, embedder, cache_dir=settings.data_path / "cache")
    else:
        from app.corpus_repo import SqlCorpusRepo
        from app.db import SessionLocal

        session = SessionLocal()
        repo = SqlCorpusRepo(session)

    config = {**th.as_dict(), "llm": settings.sarvam_llm_model, "prism": settings.sarvam_prism_model,
              "embedding": settings.embedding_model, "top_k": settings.retrieval_top_k,
              "offline_mode": settings.offline_mode, "n": len(rows)}
    print(f"Evaluating {len(rows)} claims from {args.dataset}.jsonl "
          f"({'OFFLINE heuristics - numbers are NOT meaningful' if settings.offline_mode else 'Sarvam'})")

    async with httpx.AsyncClient() as http:
        llm, prism = make_clients(http)
        deps = Deps(repo=repo, embedder=embedder, llm=llm, prism=prism)
        claims = [to_claim(i, r) for i, r in enumerate(rows)]
        t0 = time.perf_counter()
        for i in range(0, len(claims), BATCH):
            await check_claims(deps, claims[i:i + BATCH], th)
            print(f"  checked {min(i + BATCH, len(claims))}/{len(claims)}")
        secs = time.perf_counter() - t0
        items = pipeline_items(rows, claims, secs)
        m = metrics(items)
        tokens = sum(c.prism_tokens for c in claims)
        m["prism_input_tokens"] = tokens
        m["cost_inr_per_claim"] = round(tokens * PRISM_INR_PER_TOKEN / max(1, len(claims)), 5)
        if args.sweep_thresholds:
            m["sweep"] = sweep(rows, claims, th)[:15]
            best = m["sweep"][0]
            print(f"  best thresholds by F0.5: THRESH_SUPPORTED={best['supported']} THRESH_WEAK={best['weak']} "
                  f"THRESH_CONTRADICTED={best['contradicted']} (F0.5={best['f05']}). Put them in .env.")
        save(args.dataset, "pipeline", config, m, use_db=not args.memory)
        print(f"PIPELINE  precision={m['precision']} recall={m['recall']} F0.5={m['f05']} ECE={m['ece']} "
              f"abstain={m['abstention_rate']}")
        for et, d in m["catch_rate"].items():
            print(f"  caught {d['caught']}/{d['n']} {et} ({d['rate']:.0%})")

        if args.with_baseline:
            t0 = time.perf_counter()
            results = await asyncio.gather(*(baseline_judge(llm, c.text, c.passages) for c in claims))
            bsecs = time.perf_counter() - t0
            b_items = []
            for r, (label, conf, _) in zip(rows, results):
                verdict, colour = baseline_verdict(label, conf, th)
                b_items.append({"id": r["id"], "label": r["label"], "error_type": r.get("error_type"),
                                "verdict": verdict, "colour": colour, "pred": label, "conf": conf,
                                "p_supported": conf if label == "supported" else 1 - conf,
                                "seconds": bsecs / max(1, len(claims))})
            bm = metrics(b_items)
            save(args.dataset, "baseline", {**config, "mode": "llm self-report"}, bm, use_db=not args.memory)
            print(f"BASELINE  precision={bm['precision']} recall={bm['recall']} F0.5={bm['f05']} ECE={bm['ece']}")
    if session is not None:
        session.close()
    print(f"Results written to {RESULTS}")


if __name__ == "__main__":
    asyncio.run(main())
