import json

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.config import REPO_DIR
from app.db import get_session
from app.models import EvalRun

router = APIRouter(prefix="/api/eval", tags=["eval"])
RESULTS = REPO_DIR / "eval" / "results"


@router.get("/latest")
def latest(dataset: str = "test", session=Depends(get_session)) -> dict:
    out: dict = {"dataset": dataset, "pipeline": None, "baseline": None}
    for mode in ("pipeline", "baseline") if session is not None else ():
        run = session.execute(
            select(EvalRun).where(EvalRun.dataset == dataset, EvalRun.mode == mode)
            .order_by(EvalRun.created_at.desc()).limit(1)
        ).scalars().first()
        if run:
            out[mode] = {"created_at": run.created_at.isoformat(), "config": run.config, "metrics": run.metrics}
    # Fall back to results written by `run_eval.py --memory` (no database).
    path = RESULTS / f"latest-{dataset}.json"
    if path.exists():
        disk = json.loads(path.read_text(encoding="utf-8"))
        for mode in ("pipeline", "baseline"):
            d = disk.get(mode)
            if d and (out[mode] is None or d["created_at"] > out[mode]["created_at"]):
                out[mode] = d
    return out
