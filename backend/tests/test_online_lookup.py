"""Indian Kanoon lookup with a fake client: no network, no cost. The corpus is copied to a temp dir
because found documents are written into corpus/files/indiankanoon/ and the manifest."""
import asyncio
import shutil

import pytest

from app.check.pipeline import Deps, analyse
from app.clients.indiankanoon import IKUnavailable, html_to_text
from app.clients.offline import OfflinePrism
from app.config import settings
from app.ingest.embedder import HashEmbedder
from app.ingest.manifest import load_manifest
from app.ingest.pipeline import build_memory_repo

CASE_HTML = """<h2 class="doc_title">Anita Sharma vs Union Of India on 5 May, 2015</h2>
<pre>Equivalent citations: (2015) 3 SCC 100</pre>
<p>1. The appeal concerns post-dated cheques issued as security.</p>
<p>2. We hold that a post-dated cheque given as security is enforceable once the debt falls due.</p>"""

SECTION_HTML = """<h2>Section 25 in The Payment Instruments Act, 2007</h2>
<p>25. Every payment instrument returned unpaid shall be reported to the payee within fifteen days.</p>"""


class FakeIK:
    def __init__(self, fail: bool = False):
        self.fail, self.searches, self.docs = fail, [], []

    async def search(self, query, doctypes=None):
        if self.fail:
            raise IKUnavailable("Could not reach Indian Kanoon")
        self.searches.append((query, doctypes))
        if doctypes == "laws" and "payment instruments" in query.lower():
            return [{"tid": 77, "title": "Section 25 in The Payment Instruments Act, 2007"}]
        if doctypes == "judgments" and ("3 SCC 100" in query or "Sharma" in query):
            return [{"tid": 999, "title": "Anita Sharma vs Union Of India on 5 May, 2015",
                     "docsource": "Supreme Court of India"}]
        return []

    async def doc(self, tid):
        self.docs.append(int(tid))
        html = CASE_HTML if int(tid) == 999 else SECTION_HTML
        return {"doc": html, "title": "", "text": html_to_text(html)}


@pytest.fixture
def corpus(tmp_path, monkeypatch, corpus_dir):
    dst = tmp_path / "corpus"
    shutil.copytree(corpus_dir, dst, ignore=shutil.ignore_patterns("indiankanoon", "uploads"))
    monkeypatch.setattr(settings, "corpus_dir", str(dst))
    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "data"))
    return dst


def run(corpus, text, ik):
    emb = HashEmbedder(1024)
    deps = Deps(repo=build_memory_repo(corpus, emb), embedder=emb, llm=None, prism=OfflinePrism(), online=ik)
    claims, summary = asyncio.run(analyse(text, deps))
    return claims, summary


def test_case_found_online_is_added_and_used(corpus):
    ik = FakeIK()
    text = ("In Anita Sharma v. Union of India, (2015) 3 SCC 100, the Supreme Court held that a post-dated "
            "cheque given as security is enforceable once the debt falls due.")
    claims, summary = run(corpus, text, ik)
    c = claims[0]
    assert c.resolution.status == "found" and c.source.id == "ik-999"
    assert c.verdict != "fabricated"
    assert summary["online_found"] == 1
    assert "ik-999" in {e.id for e in load_manifest(corpus)}
    assert (corpus / "files/indiankanoon/ik-999.txt").exists()

    # Second run: now in the corpus, so no new API calls.
    ik2 = FakeIK()
    claims, summary = run(corpus, text, ik2)
    assert claims[0].source.id == "ik-999" and ik2.searches == [] and summary["online_lookups"] == 0


def test_statute_section_found_online(corpus):
    text = ("Under Section 25 of the Payment Instruments Act, 2007, every payment instrument returned unpaid "
            "shall be reported to the payee within fifteen days.")
    claims, _ = run(corpus, text, FakeIK())
    c = claims[0]
    assert c.resolution.status == "found", c.resolution
    assert c.source.id.startswith("ik-act-") and c.resolution.section == "25"
    assert c.verdict != "fabricated"


def test_fabricated_when_not_found_anywhere(corpus):
    text = "In Rajesh Malhotra v. Union of India, (2019) 7 SCC 412, the Supreme Court held that cheques are void."
    claims, _ = run(corpus, text, FakeIK())
    c = claims[0]
    assert c.verdict == "fabricated"
    assert "also not found on Indian Kanoon" in c.reason


def test_unreachable_api_is_not_called_fabricated(corpus):
    text = "In Rajesh Malhotra v. Union of India, (2019) 7 SCC 412, the Supreme Court held that cheques are void."
    claims, _ = run(corpus, text, FakeIK(fail=True))
    c = claims[0]
    assert c.verdict == "insufficient" and c.colour == "amber"
    assert c.resolution.status == "unverified" and "could not be reached" in c.reason


def test_local_citation_needs_no_lookup(corpus):
    ik = FakeIK()
    text = ("In Ravindra Kulkarni v. Meridian Textiles Pvt. Ltd., (2018) 4 SCC 512, the Supreme Court considered "
            "security cheques.")
    run(corpus, text, ik)
    assert ik.searches == []
