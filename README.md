# Legal Fact Checker

Checks an AI-written legal draft for **fabricated citations**, **misquotes** and **unsupported claims**.
Each claim gets a calibrated confidence score, and the tool **abstains** when the sources don't settle it.

The full specification is in [`../legal-factcheck-build-guide.md`](../legal-factcheck-build-guide.md).
This README covers how to run the project and where it differs from the guide.

```
draft ─▶ segment ─▶ citations (regex) + quotes ─▶ claims (Sarvam LLM)
      ─▶ resolve citation (DB lookup) ─▶ quote check (rapidfuzz) ─▶ hybrid retrieval (pgvector + FTS, RRF)
      ─▶ Sarvam Prism (supported / contradicted / not enough info) ─▶ rules ─▶ GREEN / AMBER / RED + fix
```

## Run everything with one command

Prerequisites: **Python 3.12+** and **Node 20+**. No Docker and no database needed.

```bash
python run.py            # Windows: you can also double-click run.bat
```

That one command:
1. creates `.env` from `.env.example` (first run only),
2. creates `backend/.venv` and installs the Python packages, and runs `npm install` in `frontend/`
   (only when something changed),
3. starts the API on http://localhost:8000 and the UI on http://localhost:3000, prints both logs
   (`[api]` / `[web]`) and opens the browser. **Ctrl+C stops both.**

Then pick **Load example draft… → demo** and click **Check draft**. The `contract-correct` and `contract-wrong` examples need Indian Kanoon on (they cite the Indian Contract Act and the Arbitration Act).

| Option | What it does |
|---|---|
| `--offline` | No Sarvam key and no 2.3 GB model: heuristics only, results not meaningful (UI work) |
| `--skip-install` | Skip the dependency check for a faster start |
| `--no-browser` | Don't open the browser |

**Real results:** put your key in `.env` (`SARVAM_API_KEY=...`) and run `python run.py` again. While the key
is empty, the launcher starts in offline mode automatically and says so. The first real start downloads
bge-m3 (~2.3 GB) and embeds the corpus. The embeddings are cached in `data/cache/`, so later starts are fast.

### Where data lives (no database)

With `DATABASE_URL` empty (the default), the backend:
- loads every enabled source in `corpus/manifest.yaml` into memory at startup,
- saves each check as `data/checks/<id>.json` (the "Recent checks" list reads these),
- takes uploads on the Sources page and reloads the corpus straight away.

To start clean, delete `data/`. After you edit `corpus/manifest.yaml` or a corpus file, restart.

### Indian Kanoon lookups (citations not in the corpus)

Put your token in `.env` as `INDIANKANOON_API_TOKEN=...` and restart. The header then shows **Indian Kanoon on**.
For every citation that the local corpus doesn't have, a check now does the following:

1. **Search.** Judgments are searched by the citation, then by the case name. A statute section is
   searched as "Section N" plus the act name, among laws.
2. **Verify.** A hit is used only after its document is fetched and it contains the cited citation, or
   carries the cited case name with a matching year. A name match on its own gives "citation mismatch",
   never a green verdict.
3. **Save.** The document goes into `corpus/files/indiankanoon/` and `corpus/manifest.yaml` (ids `ik-<docid>`;
   statute sections go into one `ik-act-<name>` source). It is part of the corpus from then on, so it is never
   paid for again. Raw API responses are also cached in `data/indiankanoon/`.
4. **Judge.** The claim is then checked against that text exactly like a local source.

What the verdict means:
- **Not in the corpus and not on Indian Kanoon:** "possibly fabricated", with the reason saying both were searched.
- **Indian Kanoon unreachable** (network, bad token, empty balance): amber "could not verify", never "fabricated".
- **More than `INDIANKANOON_MAX_LOOKUPS` distinct citations in one draft** (default 8): the rest are not
  looked up and show as "could not verify". This caps the cost of a single check.

Constitution articles are not looked up; keep the Constitution in the local corpus. If a draft cites a section that
is missing from an act you curated locally, that section is not looked up either: a local act is treated as complete.
Indian Kanoon's terms ask for "powered by IKanoon" attribution at the top of results. The report page shows it
whenever a source came from Indian Kanoon.

### Other commands (from `backend/`, using its venv)

```bash
.venv/Scripts/python scripts/smoke_sarvam.py      # check your key: one LLM call + one Prism call
.venv/Scripts/python scripts/smoke_indiankanoon.py --doc   # check your Indian Kanoon token (~Rs 0.70)
.venv/Scripts/python -m pytest -q                 # tests
.venv/Scripts/python scripts/make_eval_set.py --out ../eval/gold --n 300 --dev 100
.venv/Scripts/python scripts/run_eval.py --dataset dev  --sweep-thresholds   # copy best thresholds into .env
.venv/Scripts/python scripts/run_eval.py --dataset test --with-baseline      # shown on /eval
```
(On macOS/Linux use `.venv/bin/python`.)

### Optional: PostgreSQL instead of memory

For a large corpus you can use PostgreSQL 16 with `pgvector`. Set `DATABASE_URL` in `.env`, then from `backend/`
run `scripts/init_db.py` (applies `db/init.sql`) and `scripts/ingest_corpus.py`. Everything else stays the same.

## The sample corpus is fictional

`corpus/files/sample/` contains **four fictional documents** (a model cheque-dishonour act and three judgments of
a "Sample Supreme Court") written so the demo draft exercises every verdict. They are not real law, and their
citations must never be presented as real authorities.

Before reporting any numbers:
1. Download real sources (India Code for acts; the Supreme Court of India website for judgments), check each
   licence, add them to `corpus/manifest.yaml` (a disabled NI Act entry shows the format), and set the
   `sample-*` entries to `enabled: false`.
2. Restart `python run.py` (or run `scripts/ingest_corpus.py` if you use Postgres)
3. Regenerate `eval/gold/` with a Sarvam key (the committed files were built in offline mode from the sample
   corpus: paraphrases are verbatim) and have someone with legal knowledge spot-check at least 50 rows
   (`"checked": true`).
4. Write a new `eval/drafts/demo.txt` against the real corpus, with the four planted errors from Section 17
   of the guide.

## Where this differs from the guide

| Change | Why |
|---|---|
| `claims` has extra columns `case_name`, `quote_diff`, `quote_critical`; `sources` has `citations` (display form) | The UI shows the word diff and the correct citation; the fixer needs the citation text |
| Extra verdict `not_legal` (grey) | Rule 1 of the scorer; the guide's table already uses it |
| Rule 4b: a quote with minor, non-critical differences → amber `weak` | Section 8 says "minor differences (amber)" but the rule table had no row for it |
| A statute citation pins retrieval to that section; a missing section → `not_found` | "Section 139" with Section 138's content then fails against 139, and the fixer suggests 138 |
| A case name that matches but with a citation number not in the DB → `found` with a note; never green | A real case with the wrong reporter number is a citation error, not a fabrication |
| "Supported by a different source" second pass for weak/insufficient/contradicted claims | Implements the guide's "not supported by the case you cited, but supported by X" |
| No Docker; the database is optional (`DATABASE_URL` empty = in-memory corpus + JSON files in `data/`) | One command (`python run.py`) runs everything with no database to install |
| `corpus_repo.py` (SQL + in-memory) | Same pipeline code for both storage modes and for the tests |
| `EMBEDDING_MODEL=hash` | UI work and tests without the 2.3 GB download |
| Indian Kanoon lookup for citations not in the corpus (optional) | A corpus can never hold every judgment; "not in our corpus" alone is weak evidence of fabrication |
| `GET /api/demo-drafts` | Feeds the "Load demo draft" button from `eval/drafts/` |
| Fixes are applied client-side to a working copy, so several can be stacked before re-checking | `POST …/apply-fix` still exists for API users |
| `run.py` installs with pip into `backend/.venv`; `uv` is optional | `uv sync` still works if you prefer uv |

## Layout

```
run.py / run.bat            start backend + frontend together
db/init.sql                 optional Postgres schema (pgvector, FTS, HNSW)
corpus/manifest.yaml        sources; files under corpus/files/
eval/gold/*.jsonl           labelled claims (dev for tuning, test for reporting)
eval/drafts/demo.txt        demo draft with 4 planted errors
backend/app/check/          the pipeline: segmenter, citations, quotes, extractor, resolver,
                            retriever, judge, scorer, fixer, pipeline
backend/app/clients/        the only code that talks to Sarvam / Indian Kanoon (+ offline fakes)
backend/app/check/online.py look up missing citations on Indian Kanoon, verify, add to the corpus
backend/app/ingest/         manifest, loaders, chunker, embedder, ingest pipeline
backend/app/local_store.py  no-database mode: in-memory corpus, checks as JSON files
data/                       created at runtime: saved checks + embedding cache (gitignored)
backend/scripts/            ingest_corpus, smoke_sarvam, make_eval_set, run_eval, init_db
frontend/app/               / (check), /checks/[id] (report), /sources, /eval
```
