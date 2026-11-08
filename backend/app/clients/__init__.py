"""Thin wrappers around external APIs. Nothing else calls httpx directly."""
import httpx

from app.config import settings


class SarvamUnavailable(Exception):
    """Network failure or 429/5xx after all retries."""


class SarvamBadRequest(Exception):
    """400/403/422: a bug in our request (or a bad key). Never retried."""


def make_clients(http: httpx.AsyncClient):
    """Return (llm, prism) for the current mode."""
    if settings.offline_mode:
        from app.clients.offline import OfflineLLM, OfflinePrism

        return OfflineLLM(), OfflinePrism()
    from app.clients.sarvam_llm import SarvamLLM
    from app.clients.sarvam_prism import SarvamPrism

    return SarvamLLM(http), SarvamPrism(http)
