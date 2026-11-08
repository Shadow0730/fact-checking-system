from app.ingest.chunker import chunk_document


def test_judgment_paragraphs_keep_numbers_and_pages():
    pages = [(1, "HEADER\n1. First para text.\n2. Second para\ncontinues here."), (2, "3. Third para on page two.")]
    chunks = chunk_document(pages, "judgment")
    assert [c.para for c in chunks] == [None, "1", "2", "3"]
    assert chunks[-1].page_start == 2
    assert chunks[2].text == "2. Second para continues here."


def test_list_restarting_inside_para_is_not_a_new_para():
    text = "1. Facts.\n2. Issues are:\n1. first issue\n3. Analysis."
    paras = [c.para for c in chunk_document([(1, text)], "judgment")]
    assert paras == ["1", "2", "3"]


def test_statute_sections():
    text = "THE ACT\n138. Dishonour of cheque.\nText.\n138A. Inserted.\n139. Presumption."
    paras = [c.para for c in chunk_document([(1, text)], "statute")]
    assert paras == [None, "138", "138A", "139"]


def test_long_paragraph_is_split_but_keeps_para():
    long = "1. " + " ".join(f"Sentence number {i} is here." for i in range(400))
    chunks = chunk_document([(1, long)], "judgment", target_chars=500, max_chars=800)
    assert len(chunks) > 3
    assert all(c.para == "1" and len(c.text) <= 800 for c in chunks)
