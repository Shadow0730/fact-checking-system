# Legal Fact Checker

Checks AI-written Indian legal drafts for **fabricated citations**, **misquotes** and **unsupported claims**.
Every claim gets a verdict, a reason and a confidence score. When the sources don't settle a claim, the tool
abstains instead of guessing.

Built with FastAPI, Next.js, Sarvam (LLM and Prism) and bge-m3 embeddings. It needs no database or Docker.

## Quick start

Requires **Python 3.12+** and **Node 20+**.

```bash
python run.py        # on Windows you can also double-click run.bat
```

This creates `.env`, installs anything missing, starts the UI on http://localhost:3000 and the API on
http://localhost:8000 (docs at `/docs`), and opens the browser. Ctrl+C stops both.

In the UI, choose **Load example draft… → demo** and click **Check draft**.

**For real results**, set `SARVAM_API_KEY` in `.env` and run `python run.py` again. Without a key, the app starts
in offline mode, which uses heuristics only and is **not meaningful** beyond UI work. The first real start downloads
bge-m3 (~2.3 GB) and embeds the corpus; embeddings are cached in `data/cache/`.

| Option | Effect |
|---|---|
| `--offline` | Force offline mode: no Sarvam key, no model download |
| `--skip-install` | Skip the dependency check |
| `--no-browser` | Don't open the browser |

> **The bundled corpus is fictional.** `corpus/files/sample/` holds four invented documents written to exercise
> every verdict in the demo. Never present their citations as real authorities. See
> [Using a real corpus](#using-a-real-corpus).

## How it works

1. **Extract:** split the draft into segments, then pull out citations (regex), quotes, and claims (Sarvam LLM).
2. **Resolve:** look up each citation in the corpus, then on Indian Kanoon if enabled.
3. **Compare quotes:** fuzzy-match quoted text against the source (rapidfuzz).
4. **Retrieve:** run vector and keyword search and merge the results with reciprocal rank fusion.
5. **Judge:** Sarvam Prism decides whether the evidence supports the claim, contradicts it, or doesn't settle it.
6. **Score:** ordered rules assign the verdict, and the tool suggests a fix where it can.

| Verdict | Colour | Meaning |
|---|---|---|
| Possibly fabricated | Red | Citation not found in any source that was searched |
| Misquote | Red | Quote doesn't match the source, or a word that changes legal meaning differs |
| Contradicted | Red | The source says otherwise |
| Verified | Green | Prism's support probability is at least `THRESH_SUPPORTED` (default 0.90) |
| Weak support | Amber | Partial support (at least `THRESH_WEAK`, default 0.60), minor quote differences, or a real case with the wrong citation number |
| Insufficient sources | Amber | Abstained: not enough evidence, or the citation could not be checked |
| Not a legal claim | Grey | A fact about the matter, not checkable against the law |

## Configuration

Settings live in `.env`; [`.env.example`](.env.example) documents all of them.

| Variable | Purpose |
|---|---|
| `SARVAM_API_KEY` | Enables real claim extraction and judging |
| `INDIANKANOON_API_TOKEN` | Enables Indian Kanoon lookups (optional) |
| `INDIANKANOON_MAX_LOOKUPS` | Most distinct citations looked up per check (default 8) |
| `DATABASE_URL` | Use PostgreSQL instead of memory (optional) |
| `EMBEDDING_MODEL` | Embedding model; `hash` skips the download (UI work and tests only) |
| `THRESH_*`, `QUOTE_*` | Verdict thresholds |

### Storage

With `DATABASE_URL` empty, the corpus in `corpus/manifest.yaml` loads into memory at startup and each check is saved
as `data/checks/<id>.json`. Restart after editing the manifest or a corpus file. Files uploaded on the Sources page
(`.pdf`, `.docx`, `.txt`, `.md`) take effect immediately. To clear saved checks and caches, delete `data/`.

For a large corpus, use PostgreSQL 16 with `pgvector`: set `DATABASE_URL`, then run `scripts/init_db.py` and
`scripts/ingest_corpus.py` from `backend/`.

### Indian Kanoon lookups

With a token set, the header shows **Indian Kanoon on**, and citations missing from the corpus are handled as follows:

1. **Search** judgments by citation, then by case name. Statute sections are searched by section number and act name.
2. **Verify** by fetching the document. It must contain the citation, or the case name with a matching year. A name
   match alone gives a citation mismatch, never a green verdict.
3. **Save** it to `corpus/files/indiankanoon/` and `corpus/manifest.yaml`, so it is only paid for once.
4. **Judge** the claim against that text like any local source.

| Lookup result | Outcome |
|---|---|
| Not in the corpus or on Indian Kanoon | Possibly fabricated |
| Indian Kanoon unreachable (network, bad token, empty balance) | Could not verify (amber), never fabricated |
| Over the per-check lookup limit | Could not verify (amber) |

The `contract-*` example drafts need lookups on, because they cite real acts that the sample corpus doesn't contain.

Constitution articles are not looked up, so keep the Constitution in the local corpus. A locally curated act is
treated as complete, so a section missing from it is not looked up either. Indian Kanoon's terms require
"powered by IKanoon" attribution, which the report page shows whenever a source came from there.

## Using a real corpus

Do these steps before reporting any numbers:

1. Download real sources (India Code for acts, the Supreme Court of India website for judgments) and check each licence.
2. Add them to `corpus/manifest.yaml` (the disabled `ni-act-1881` entry shows the format) and set the `sample-*`
   entries to `enabled: false`.
3. Restart `python run.py`, or run `scripts/ingest_corpus.py` if you use Postgres.
4. Regenerate `eval/gold/` with a Sarvam key, since the committed files were built offline from the sample corpus and
   their paraphrases are verbatim. Have someone with legal knowledge spot-check at least 50 rows (`"checked": true`).
5. Write a new `eval/drafts/demo.txt` against the real corpus, with planted errors for each red verdict.

## Development

Run these from `backend/`. On macOS/Linux, use `.venv/bin/python`.

```bash
.venv/Scripts/python -m pytest -q                            # tests
.venv/Scripts/python scripts/smoke_sarvam.py                 # check the Sarvam key
.venv/Scripts/python scripts/smoke_indiankanoon.py --doc     # check the Indian Kanoon token (~Rs 0.70)

.venv/Scripts/python scripts/make_eval_set.py --out ../eval/gold --n 300 --dev 100
.venv/Scripts/python scripts/run_eval.py --dataset dev --sweep-thresholds   # copy the best thresholds into .env
.venv/Scripts/python scripts/run_eval.py --dataset test --with-baseline     # results appear on /eval
```

```
run.py, run.bat       start backend and frontend together
backend/app/check/    pipeline: segmenter, citations, quotes, extractor, resolver, online lookup,
                      retriever, judge, scorer, fixer
backend/app/clients/  the only code that calls Sarvam or Indian Kanoon, plus offline fakes
backend/app/ingest/   manifest, loaders, chunker, embedder
backend/app/routers/  checks, sources, eval, health
backend/scripts/      smoke tests, ingestion, evaluation
frontend/app/         pages: / (check), /checks/[id] (report), /sources, /eval
corpus/               manifest.yaml and source files
eval/                 gold claims (dev for tuning, test for reporting) and example drafts
db/init.sql           optional Postgres schema
data/                 created at runtime: saved checks and caches (gitignored)
```
