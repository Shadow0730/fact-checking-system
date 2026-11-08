"""Hindi drafts: statute citations in Devanagari map to the same keys as English ones."""
from app.check.citations import citation_key, find_citations
from app.check.segmenter import segment

EN = "ACT|indian contract act|1872|S|73"


def test_hindi_act_first():
    assert citation_key("भारतीय संविदा अधिनियम, 1872 की धारा 73 के अनुसार") == EN


def test_hindi_section_first_and_devanagari_digits():
    assert citation_key("धारा ७३, भारतीय संविदा अधिनियम, १८७२") == EN


def test_hindi_arbitration_spellings():
    for name in ("माध्यस्थम् और सुलह अधिनियम", "मध्यस्थता एवं सुलह अधिनियम"):
        assert citation_key(f"{name}, 1996 की धारा 7") == "ACT|arbitration and conciliation act|1996|S|7"


def test_hindi_offsets_point_at_original_text():
    t = "यह करार है। भारतीय संविदा अधिनियम, 1872 की धारा 27 देखें।"
    (c,) = find_citations(t)
    assert t[c.char_start:c.char_end] == c.raw and c.raw.endswith("धारा 27")


def test_danda_splits_sentences():
    t = "पहला वाक्य है। दूसरा वाक्य है।"
    assert [s.text for s in segment(t)] == ["पहला वाक्य है।", "दूसरा वाक्य है।"]
