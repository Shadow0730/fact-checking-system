from app.check.scorer import Thresholds, score
from app.check.types import ChunkInfo, ClaimWork, QuoteResult, Resolution, SourceInfo

TH = Thresholds(supported=0.9, weak=0.6, contradicted=0.5, quote_exact=97, quote_near=85)
SRC = SourceInfo("kulkarni", "Kulkarni v. Meridian", "judgment", citations=["(2018) 4 SCC 512"])
EV = ChunkInfo(7, "kulkarni", "Kulkarni v. Meridian", 4, "text", para="5")


def claim(**kw) -> ClaimWork:
    base = dict(ord=1, text="claim", claim_type="holding", char_start=0, char_end=5,
                citation_raw="(2018) 4 SCC 512", resolution=Resolution("found", SRC), evidence=EV,
                support_probs={"supported": 0.95, "contradicted": 0.02, "not_enough_info": 0.03})
    base.update(kw)
    return ClaimWork(**base)


def probs(s, c, n):
    return {"supported": s, "contradicted": c, "not_enough_info": n}


def exact():
    return QuoteResult(100, "m", 7, [{"op": "equal", "draft": "a", "source": "a"}], False, False)


def test_rule1_fact_is_grey():
    c = claim(claim_type="fact")
    score(c, TH)
    assert (c.verdict, c.colour) == ("not_legal", "grey")


def test_rule2_fabricated_beats_high_support():
    c = claim(resolution=Resolution("not_found"))
    score(c, TH)
    assert (c.verdict, c.colour) == ("fabricated", "red")
    assert "possibly fabricated" in c.reason


def test_rule2_case_name_only_also_counts_as_citation():
    c = claim(citation_raw=None, case_name="Nobody v. Nothing", resolution=Resolution("not_found"))
    score(c, TH)
    assert c.verdict == "fabricated"


def test_rule3_misquote_low_score():
    c = claim(quote_text="q", quote=QuoteResult(60, "m", 7, [], False, True))
    score(c, TH)
    assert (c.verdict, c.colour) == ("misquote", "red")


def test_rule3_misquote_critical_word_despite_high_score():
    diff = [{"op": "replace", "draft": "may", "source": "shall"}]
    c = claim(quote_text="q", quote=QuoteResult(96, "m", 7, diff, True, True))
    score(c, TH)
    assert c.verdict == "misquote"
    assert "'may' in the draft is 'shall' in the source" in c.reason


def test_rule4_contradicted():
    c = claim(support_probs=probs(0.2, 0.7, 0.1))
    score(c, TH)
    assert (c.verdict, c.colour) == ("contradicted", "red")
    assert "para 5" in c.reason


def test_rule4b_minor_quote_difference_is_amber():
    diff = [{"op": "replace", "draft": "filing", "source": "presentation"}]
    c = claim(quote_text="q", quote=QuoteResult(92, "m", 7, diff, False, True))
    score(c, TH)
    assert (c.verdict, c.colour) == ("weak", "amber")


def test_rule5_verified():
    c = claim()
    score(c, TH)
    assert (c.verdict, c.colour) == ("verified", "green")
    assert c.confidence == 0.95


def test_rule5_verified_with_exact_quote():
    c = claim(quote_text="q", quote=exact())
    score(c, TH)
    assert c.verdict == "verified"


def test_rule6_weak():
    c = claim(support_probs=probs(0.7, 0.1, 0.2))
    score(c, TH)
    assert (c.verdict, c.colour) == ("weak", "amber")


def test_rule7_abstains():
    c = claim(support_probs=probs(0.3, 0.1, 0.6))
    score(c, TH)
    assert (c.verdict, c.colour) == ("insufficient", "amber")


def test_ambiguous_adds_note_without_changing_verdict():
    c = claim(resolution=Resolution("ambiguous", note="Did you mean Kulkarni v. Meridian?"),
              support_probs=probs(0.3, 0.1, 0.6))
    score(c, TH)
    assert c.verdict == "insufficient"
    assert "Did you mean" in c.reason


def test_mismatched_citation_number_never_green():
    c = claim(resolution=Resolution("found", SRC, mismatch=True, note="listed as (2018) 4 SCC 512"))
    score(c, TH)
    assert c.verdict == "weak"


def test_contradicted_takes_priority_over_support_rules_order():
    c = claim(support_probs=probs(0.5, 0.5, 0.0))
    score(c, TH)
    assert c.verdict == "contradicted"
