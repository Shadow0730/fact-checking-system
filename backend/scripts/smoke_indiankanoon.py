"""Check that INDIANKANOON_API_TOKEN works: one search (about Rs 0.50), plus one document with --doc (about Rs 0.20).

    .venv/Scripts/python scripts/smoke_indiankanoon.py [--doc] [--query "..."]

Responses are cached in data/indiankanoon/, so re-running the same query costs nothing.
"""
import argparse
import asyncio
import os

os.environ.setdefault("OFFLINE_MODE", "true")   # this script never calls Sarvam, so no key is needed

import _bootstrap  # noqa: F401
import httpx

from app.clients.indiankanoon import IKUnavailable, IndianKanoon, strip_tags
from app.config import settings


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--query", default='"Section 138" negotiable instruments act')
    ap.add_argument("--doctypes", default="laws")
    ap.add_argument("--doc", action="store_true", help="also fetch the first result's document")
    args = ap.parse_args()
    if not settings.indiankanoon_api_token:
        raise SystemExit("INDIANKANOON_API_TOKEN is empty in .env")
    async with httpx.AsyncClient() as http:
        ik = IndianKanoon(http)
        try:
            hits = await ik.search(args.query, args.doctypes)
            print(f"search OK: {len(hits)} results for {args.query!r} (doctypes {args.doctypes})")
            for h in hits[:5]:
                print(f"  tid={h.get('tid'):<10} {strip_tags(h.get('title', ''))}")
            if args.doc and hits:
                d = await ik.doc(hits[0]["tid"])
                print(f"\ndoc OK: keys={sorted(k for k in d if k != 'text')}")
                print(d["text"][:600])
        except IKUnavailable as e:
            raise SystemExit(f"FAILED: {e}") from e
        print(f"\npaid requests made: {ik.requests} (cached responses are free)")


if __name__ == "__main__":
    asyncio.run(main())
