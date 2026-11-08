from app.check.segmenter import segment


def test_abbreviations_do_not_split():
    text = ("In Kesavananda Bharati v. State of Kerala, the Court held so. "
            "Orion Agro Pvt. Ltd. issued the cheque under S. 138 of the Act. See para. 5 at p. 12.")
    sents = segment(text)
    assert len(sents) == 3, [s.text for s in sents]
    assert sents[0].text.startswith("In Kesavananda Bharati v. State of Kerala")


def test_offsets_map_back_to_original():
    text = "HEADING\n\nFirst sentence here. Second one, citing Ravindra Kulkarni v. Meridian Ltd.\nThird line."
    for s in segment(text):
        assert text[s.char_start:s.char_end] == s.text


def test_headings_stay_separate():
    text = "LEGAL NOTICE\nThe drawer shall be liable."
    sents = segment(text)
    assert [s.text for s in sents] == ["LEGAL NOTICE", "The drawer shall be liable."]
    assert [s.id for s in sents] == ["S1", "S2"]
