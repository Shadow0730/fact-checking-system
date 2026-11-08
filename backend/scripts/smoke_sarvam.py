"""One LLM call + one Prism call, to check the key and the request shapes work.

    uv run python scripts/smoke_sarvam.py
"""
import asyncio
import json
import time

import _bootstrap  # noqa: F401
import httpx

from app.clients.sarvam_llm import SarvamLLM
from app.clients.sarvam_prism import SarvamPrism
from app.config import settings


async def main() -> None:
    if settings.offline_mode:
        raise SystemExit("OFFLINE_MODE=true: nothing to smoke-test. Set it to false and fill SARVAM_API_KEY.")
    async with httpx.AsyncClient() as http:
        t0 = time.perf_counter()
        data, tokens = await SarvamLLM(http).chat_json("Reply with one JSON object only.",
                                                       'Return {"ok": true}', max_tokens=200)
        print(f"LLM   ({settings.sarvam_llm_model}) {time.perf_counter() - t0:.2f}s tokens={tokens}: {data}")

        t0 = time.perf_counter()
        answers, tokens = await SarvamPrism(http).decide(
            {"claim": "A post-dated cheque is a cheque for the purpose of the offence.",
             "passages": [{"id": "p1", "text": "A post-dated cheque is a cheque for this purpose and is drawn "
                                               "on the date it bears."}]},
            {"support": {"type": "choice",
                         "instructions": "Using ONLY the passages, do they support the claim?",
                         "criteria": {"supported": "The passages support the claim",
                                      "contradicted": "The passages contradict the claim",
                                      "not_enough_info": "The passages do not settle the claim"}}},
        )
        print(f"Prism ({settings.sarvam_prism_model}) {time.perf_counter() - t0:.2f}s input_tokens={tokens}:")
        print(json.dumps(answers, indent=2))
        probs = answers["support"].get("probabilities", {})
        assert probs, "Prism returned no probabilities: check the response shape against docs.sarvam.ai"
        print("OK: both calls work.")


if __name__ == "__main__":
    asyncio.run(main())
