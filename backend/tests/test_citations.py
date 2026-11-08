import pytest

from app.check.citations import citation_key, find_citations


@pytest.mark.parametrize("text,key", [
    ("AIR 1973 SC 1461", "AIR|1973|SC|1461"),
    ("AIR1973 SC 1461", "AIR|1973|SC|1461"),
    ("AIR 1950 Bom 23", "AIR|1950|BOM|23"),
    ("(2017) 10 SCC 1", "SCC|2017|10|1"),
    ("(2017)10 SCC 1", "SCC|2017|10|1"),
    ("[1973] Supp. 1 SCR 1", "SCR|1973|1|1"),
    ("[1973] Supp 1 SCR 1", "SCR|1973|1|1"),
    ("[1985] 3 SCR 844", "SCR|1985|3|844"),
    ("2023 INSC 123", "INSC|2023|123"),
    ("Section 138 of the Negotiable Instruments Act, 1881", "ACT|negotiable instruments act|1881|S|138"),
    ("Section 138 of the Negotiable Instruments Act 1881", "ACT|negotiable instruments act|1881|S|138"),
    ("S. 138(1) of the NI Act", "ACT|ni act||S|138"),
    ("Section 5(1) of the Model Cheque Dishonour Act, 2020", "ACT|model cheque dishonour act|2020|S|5"),
    ("Article 21", "CONST|ART|21"),
    ("Art. 14", "CONST|ART|14"),
])
def test_formats(text, key):
    assert citation_key(text) == key


def test_no_false_positive_on_contract_clause():
    assert find_citations("Section 3 of this Agreement governs payment.") == []


def test_offsets_point_at_original_text():
    text = "As held in X v. Y, (2016) 10 SCC 458, and under Article 21 of the Constitution."
    cites = find_citations(text)
    assert [c.kind for c in cites] == ["SCC", "CONST"]
    for c in cites:
        assert text[c.char_start:c.char_end] == c.raw


def test_multiple_in_one_sentence_sorted():
    text = "AIR 1973 SC 1461 and (2017) 10 SCC 1 and 2023 INSC 123."
    assert [c.kind for c in find_citations(text)] == ["AIR", "SCC", "INSC"]
