"""Full analyse() in OFFLINE_MODE on the fictional sample corpus and the demo draft."""
from pathlib import Path

import pytest

from app.check.pipeline import Deps, analyse
from app.clients.offline import OfflinePrism

DEMO = Path(__file__).resolve().parents[2] / "eval" / "drafts" / "demo.txt"


@pytest.fixture(scope="module")
def result(memory_repo):
    import asyncio

    repo, emb = memory_repo
    text = DEMO.read_text(encoding="utf-8")
    claims, summary = asyncio.run(analyse(text, Deps(repo=repo, embedder=emb, llm=None, prism=OfflinePrism())))
    return text, claims, summary


def _claim_containing(claims, needle):
    found = [c for c in claims if needle in c.text]
    assert found, f"no claim containing {needle!r}: {[c.text[:60] for c in claims]}"
    return found[0]


def test_summary_counts(result):
    _, claims, summary = result
    assert summary["claims"] == len(claims) >= 10
    assert sum(summary[v] for v in ("verified", "weak", "insufficient", "misquote", "contradicted",
                                    "fabricated", "not_legal")) == len(claims)


def test_offsets_are_exact(result):
    text, claims, _ = result
    for c in claims:
        assert 0 <= c.char_start < c.char_end <= len(text)


def test_planted_fabricated_citation_is_red(result):
    _, claims, _ = result
    c = _claim_containing(claims, "(2019) 7 SCC 412")
    assert (c.verdict, c.colour) == ("fabricated", "red")
    assert c.fix and c.fix["kind"] in ("remove_claim", "replace_citation")


def test_planted_misquote_is_red_with_diff(result):
    _, claims, _ = result
    c = _claim_containing(claims, "the drawer may be liable")
    assert c.citation_status == "found"
    assert c.verdict == "misquote"
    assert c.quote.critical
    assert c.fix["kind"] == "replace_quote" and "shall be liable" in c.fix["text"]


def test_planted_wrong_section_is_not_green(result):
    _, claims, _ = result
    c = _claim_containing(claims, "Under Section 4 of the Model Cheque")
    assert c.citation_status == "found" and c.resolution.section == "4"
    assert c.colour != "green"


def test_planted_contradiction_is_red(result):
    _, claims, _ = result
    c = _claim_containing(claims, "every director of a company is liable")
    assert c.verdict == "contradicted"


def test_true_claim_is_verified(result):
    _, claims, _ = result
    c = _claim_containing(claims, "cause of action arises only when the drawer fails to pay")
    assert c.verdict == "verified"
    assert c.evidence and c.evidence.para == "4"
