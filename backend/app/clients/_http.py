"""Shared retry policy: retry 429/502/503/504 and network errors; never 400/403/422."""
import asyncio

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_random_exponential

from app.clients import SarvamBadRequest, SarvamUnavailable
from app.config import settings
from app.logging import get_logger

log = get_logger(__name__)
RETRYABLE = {429, 500, 502, 503, 504}

_sem: asyncio.Semaphore | None = None


def semaphore() -> asyncio.Semaphore:
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(settings.sarvam_max_concurrency)
    return _sem


def _retryable(e: BaseException) -> bool:
    if isinstance(e, httpx.HTTPStatusError):
        return e.response.status_code in RETRYABLE
    return isinstance(e, (httpx.TimeoutException, httpx.TransportError))


async def post_json(http: httpx.AsyncClient, path: str, body: dict) -> dict:
    url = settings.sarvam_base_url.rstrip("/") + path
    headers = {"api-subscription-key": settings.sarvam_api_key, "Content-Type": "application/json"}
    try:
        async with semaphore():
            async for attempt in AsyncRetrying(retry=retry_if_exception(_retryable),
                                               wait=wait_random_exponential(multiplier=1, max=30),
                                               stop=stop_after_attempt(5), reraise=True):
                with attempt:
                    r = await http.post(url, headers=headers, json=body, timeout=settings.sarvam_timeout_s)
                    r.raise_for_status()
                    return r.json()
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code in RETRYABLE:
            raise SarvamUnavailable(f"Sarvam returned {code} after retries") from e
        log.error("sarvam bad request", extra={"kv": {"status": code, "path": path,
                                                     "response": e.response.text[:2000],
                                                     "request": str(body)[:4000]}})
        raise SarvamBadRequest(f"Sarvam returned {code}: {e.response.text[:300]}") from e
    except (httpx.TimeoutException, httpx.TransportError) as e:
        raise SarvamUnavailable(f"Could not reach Sarvam: {e!r}") from e
    raise SarvamUnavailable("unreachable")  # pragma: no cover
