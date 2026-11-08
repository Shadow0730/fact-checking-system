"""Quote marks in a contract (a defined term, a description of services) are not quotations of the law."""
import asyncio

from app.check.extractor import _build, is_attributed
from app.check.pipeline import Deps, analyse
from app.check.quotes import find_quotes
from app.clients.offline import OfflinePrism

CONTRACT = ("3. Scope of Work\nThe Contractor agrees to perform the work described as 'design and build a "
            "customer-facing analytics dashboard: UI design in Figma, frontend development in React, and "
            "integrating it with our existing REST APIs' (the Services) on a project basis.")


def test_unattributed_quote_is_not_a_quotation():
    assert not is_attributed(CONTRACT, False, None)
    # In the real report the LLM returned the quoted phrase and typed the claim as a "quote".
    llm_quote = CONTRACT.split("'")[1]
    c = _build(1, CONTRACT, "quote", 0, len(CONTRACT), [], find_quotes(CONTRACT), llm_quote=llm_quote)
    assert c.quote_text is None and c.claim_type == "fact"


def test_contract_description_is_never_a_misquote(memory_repo):
    repo, emb = memory_repo
    claims, _ = asyncio.run(analyse(CONTRACT, Deps(repo=repo, embedder=emb, llm=None, prism=OfflinePrism())))
    assert all(c.verdict != "misquote" for c in claims)


def test_attributed_misquote_is_still_caught(memory_repo):
    repo, emb = memory_repo
    text = ('In Ravindra Kulkarni v. Meridian Textiles Pvt. Ltd., (2018) 4 SCC 512, the Court held that "where a '
            'cheque is drawn in discharge of a debt that has become due on the date of its presentation, the drawer '
            'may be liable under Section 3, notwithstanding that the cheque was described as security."')
    claims, _ = asyncio.run(analyse(text, Deps(repo=repo, embedder=emb, llm=None, prism=OfflinePrism())))
    assert any(c.verdict == "misquote" and c.quote and c.quote.critical for c in claims)
