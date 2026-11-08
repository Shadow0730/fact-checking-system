import pytest

from app.check.retriever import retrieve, rrf


def test_rrf_rewards_agreement():
    assert rrf([1, 2, 3], [3, 4, 1])[:2] == [1, 3]


def test_memory_retrieval_finds_planted_paragraph(memory_repo):
    repo, emb = memory_repo
    q = "a director is not liable just because he holds the office; specific averments are needed"
    hits = retrieve(repo, q, emb.embed([q])[0], top_k=3)
    assert hits[0].source_id == "sample-menon-2021"
    assert hits[0].para == "3"


def test_memory_retrieval_filters_by_source(memory_repo):
    repo, emb = memory_repo
    q = "complaint within one month of the cause of action"
    hits = retrieve(repo, q, emb.embed([q])[0], source_id="sample-kulkarni-2018")
    assert hits and all(h.source_id == "sample-kulkarni-2018" for h in hits)


def test_cited_statute_section_is_pinned(memory_repo):
    repo, emb = memory_repo
    q = "anything at all"
    hits = retrieve(repo, q, emb.embed([q])[0], source_id="sample-cheque-act-2020", section="4")
    assert [h.para for h in hits] == ["4"]


@pytest.mark.db
def test_db_retrieval_returns_planted_passage():
    from app.corpus_repo import SqlCorpusRepo
    from app.db import session_scope
    from app.ingest.embedder import get_embedder

    with session_scope() as s:
        repo = SqlCorpusRepo(s)
        if not repo.sources():
            pytest.skip("corpus not ingested")
        q = "a director is not liable merely by being a director"
        hits = retrieve(repo, q, get_embedder().embed([q])[0], top_k=5)
        assert any(h.source_id == "sample-menon-2021" for h in hits)
