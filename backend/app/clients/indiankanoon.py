"""Indian Kanoon API client (https://api.indiankanoon.org/documentation/).

Every response is cached on disk under data/indiankanoon/, so a search or a document is paid for once.
Only this module talks to Indian Kanoon.
"""
import asyncio
import hashlib
import json
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

import httpx

from app.config import settings
from app.logging import get_logger

log = get_logger(__name__)
RETRYABLE = {429, 500, 502, 503, 504}


class IKUnavailable(Exception):
    """Indian Kanoon could not be reached, rejected the token, or the balance ran out."""


class IndianKanoon:
    def __init__(self, http: httpx.AsyncClient, token: str | None = None, cache_dir: Path | None = None):
        self.http = http
        self.token = token if token is not None else settings.indiankanoon_api_token
        self.base = settings.indiankanoon_base_url.rstrip("/")
        self.cache = cache_dir or settings.data_path / "indiankanoon"
        self.cache.mkdir(parents=True, exist_ok=True)
        self._sem = asyncio.Semaphore(3)
        self.requests = 0                    # paid requests made by this process (not cache hits)

    async def _post(self, path: str, params: dict) -> dict:
        headers = {"Authorization": f"Token {self.token}", "Accept": "application/json"}
        url = f"{self.base}{path}"
        last: Exception | None = None
        async with self._sem:
            for attempt in range(3):
                try:
                    r = await self.http.post(url, params=params, headers=headers,
                                             timeout=settings.indiankanoon_timeout_s)
                except (httpx.TimeoutException, httpx.TransportError) as e:
                    last = e
                else:
                    if r.status_code < 400:
                        self.requests += 1
                        try:
                            return r.json()
                        except ValueError as e:
                            raise IKUnavailable(f"Indian Kanoon returned non-JSON for {path}") from e
                    if r.status_code not in RETRYABLE:
                        log.error("indian kanoon error", extra={"kv": {"status": r.status_code, "path": path,
                                                                       "body": r.text[:300]}})
                        hint = " (check INDIANKANOON_API_TOKEN and your balance)" if r.status_code in (401, 403) else ""
                        raise IKUnavailable(f"Indian Kanoon returned {r.status_code}{hint}")
                    last = httpx.HTTPStatusError(str(r.status_code), request=r.request, response=r)
                await asyncio.sleep(1.5 * (attempt + 1))
        raise IKUnavailable(f"Could not reach Indian Kanoon: {last!r}")

    def _cached(self, name: str) -> dict | None:
        p = self.cache / name
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                return None
        return None

    def _store(self, name: str, data: dict) -> None:
        (self.cache / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    async def search(self, query: str, doctypes: str | None = None) -> list[dict]:
        """First page of results: [{tid, title, headline, docsource, ...}]."""
        form = f"{query} doctypes: {doctypes}" if doctypes else query
        name = "search-" + hashlib.sha256(form.encode()).hexdigest()[:24] + ".json"
        data = self._cached(name)
        if data is None:
            data = await self._post("/search/", {"formInput": form, "pagenum": 0})
            self._store(name, data)
        return [d for d in data.get("docs") or [] if d.get("tid")]

    async def doc(self, tid: int | str) -> dict:
        """{'doc': <html>, 'title': ..., ...} plus 'text' (plain text) added here."""
        name = f"doc-{int(tid)}.json"
        data = self._cached(name)
        if data is None:
            data = await self._post(f"/doc/{int(tid)}/", {})
            self._store(name, data)
        data["text"] = html_to_text(data.get("doc") or "")
        return data


# ── HTML → plain text ─────────────────────────────────────────────────────────
_BLOCK = {"p", "div", "br", "pre", "blockquote", "h1", "h2", "h3", "h4", "li", "tr", "table", "section"}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in _BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.out.append(data)


def html_to_text(html: str) -> str:
    p = _Text()
    p.feed(html)
    text = unescape("".join(p.out)).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def strip_tags(s: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()
