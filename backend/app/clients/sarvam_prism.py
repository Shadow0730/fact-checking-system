"""Sarvam Prism decision model: decide(state, questions) -> (answers, input_tokens).

Each question may only carry `type`, `instructions` and `criteria`; anything else is a 422.
Threshold on the RAW `probabilities`, not on `confidence` (which is rescaled for n options).
"""
import httpx

from app.clients._http import post_json
from app.config import settings

ALLOWED_QUESTION_KEYS = {"type", "instructions", "criteria"}


def validate_questions(questions: dict) -> None:
    for name, q in questions.items():
        extra = set(q) - ALLOWED_QUESTION_KEYS
        if extra:
            raise ValueError(f"Prism question {name!r} has unsupported keys {sorted(extra)}")
        if q.get("type") == "choice" and not (2 <= len(q.get("criteria", {})) <= 255):
            raise ValueError(f"Prism choice question {name!r} needs 2-255 options")


class SarvamPrism:
    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    async def decide(self, state: dict | str, questions: dict) -> tuple[dict, int]:
        validate_questions(questions)
        data = await post_json(self.http, settings.sarvam_prism_path,
                               {"model": settings.sarvam_prism_model, "state": state, "questions": questions})
        return data["answers"], int((data.get("usage") or {}).get("input_tokens") or 0)
