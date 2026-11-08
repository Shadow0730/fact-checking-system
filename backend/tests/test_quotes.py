from app.check.quotes import find_quotes, quote_is_exact, verify_quote
from app.check.types import ChunkInfo

SOURCE = (
    "5. Where a cheque is drawn in discharge of a debt that has become due on the date of its "
    "presentation, the drawer shall be liable under Section 3, notwithstanding that the cheque "
    "was described as security. A post-dated cheque is a cheque for this purpose."
)
CHUNKS = [
    ChunkInfo(1, "s", "Source", 0, "1. Unrelated opening paragraph about the facts of the appeal."),
    ChunkInfo(2, "s", "Source", 1, SOURCE),
]


def test_exact_quote():
    r = verify_quote("the drawer shall be liable under Section 3, notwithstanding that the cheque", CHUNKS)
    assert r.score >= 97 and not r.has_diff and not r.critical
    assert r.chunk_id == 2
    assert quote_is_exact(r, 97)
    assert r.match.startswith("the drawer shall be liable")


def test_curly_quotes_and_case_still_exact():
    r = verify_quote("The Drawer shall be liable under Section 3 – notwithstanding that the cheque", CHUNKS)
    assert quote_is_exact(r, 97)


def test_one_changed_word_is_near_and_flagged():
    r = verify_quote("a debt that has become due on the date of its filing, the drawer shall be liable", CHUNKS)
    assert 85 <= r.score < 97
    assert r.has_diff and not r.critical
    assert any(op["op"] == "replace" and op["draft"] == "filing" for op in r.diff)


def test_shall_to_may_is_critical_despite_high_score():
    r = verify_quote("where a cheque is drawn in discharge of a debt that has become due on the date of its "
                     "presentation, the drawer may be liable under Section 3", CHUNKS)
    assert r.score >= 85
    assert r.critical
    assert {"op": "replace", "draft": "may", "source": "shall"} in r.diff


def test_number_change_is_critical():
    r = verify_quote("the drawer shall be liable under Section 4, notwithstanding that the cheque", CHUNKS)
    assert r.critical


def test_unrelated_text_is_low():
    r = verify_quote("the limitation period for filing a suit for specific performance is three years", CHUNKS)
    assert r.score < 85


def test_dehyphenation_across_line_break():
    chunks = [ChunkInfo(9, "s", "S", 0, "the accused may rebut the presump-\ntion on a preponderance of probabilities")]
    r = verify_quote("the accused may rebut the presumption on a preponderance of probabilities", chunks)
    assert quote_is_exact(r, 97)


def test_find_quotes_skips_short_defined_terms():
    text = 'The "Lessee" agreed. The Court said “the drawer shall be liable under Section 3 always”.'
    qs = find_quotes(text)
    assert len(qs) == 1
    assert qs[0].text.startswith("the drawer shall")
    assert text[qs[0].char_start:qs[0].char_end].startswith("the drawer")
