"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import ClaimPanel from "@/components/ClaimPanel";
import DraftViewer from "@/components/DraftViewer";
import SummaryBar from "@/components/SummaryBar";
import { isIK } from "@/lib/indiankanoon";
import { getCheck, runCheck } from "@/lib/api";
import type { Claim, Colour, Report } from "@/lib/types";
import { COLOUR_CLASS, SEVERITY, VERDICT_META } from "@/lib/verdicts";

type Filter = "all" | Colour;

/** Apply a fix to the working copy of the draft (only exact quote text and citations are replaced). */
function applyToText(text: string, c: Claim): string | null {
  const f = c.fix;
  if (!f) return null;
  const [from, to] =
    f.kind === "replace_quote" ? [c.quote_text, f.text] : f.kind === "replace_citation" ? [c.citation_raw, f.citation] : [null, null];
  if (!from || !to || !text.includes(from)) return null;
  return text.replace(from, to);
}

export default function ReportPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [working, setWorking] = useState<string | null>(null);
  const [applied, setApplied] = useState<Set<string>>(new Set());
  const [rechecking, setRechecking] = useState(false);

  useEffect(() => {
    getCheck(id)
      .then((r) => {
        setReport(r);
        const worst = [...r.claims].sort((a, b) => SEVERITY[b.colour] - SEVERITY[a.colour] || a.ord - b.ord)[0];
        setSelected(worst?.id ?? null);
      })
      .catch((e) => setError(e.message));
  }, [id]);

  const claims = useMemo(() => report?.claims ?? [], [report]);
  const current = claims.find((c) => c.id === selected) ?? null;
  const visible = (c: Claim) => filter === "all" || c.colour === filter;
  const listed = claims.filter(visible).sort((a, b) => a.char_start - b.char_start);

  function select(cid: string) {
    setSelected(cid);
    document.getElementById(`claim-${cid}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function onApplyFix(c: Claim) {
    const base = working ?? report!.input_text;
    const next = applyToText(base, c);
    if (next === null) return setError("Could not locate the text to replace in the draft.");
    setWorking(next);
    setApplied(new Set(applied).add(c.id));
  }

  async function recheck() {
    if (!working) return;
    setRechecking(true);
    try {
      const r = await runCheck(working, `${report?.title || "Draft"} (fixed)`);
      router.push(`/checks/${r.id}`);
    } catch (e) {
      setError((e as Error).message);
      setRechecking(false);
    }
  }

  if (error && !report) return <p className="rounded-lg bg-[var(--red-bg)] text-[var(--red-fg)] p-3">{error}</p>;
  if (!report) return <p className="text-[var(--muted)]">Loading report…</p>;
  if (report.status === "failed") {
    return (
      <div className="space-y-3">
        <h1 className="text-xl font-bold">This check failed</h1>
        <p className="rounded-lg bg-[var(--red-bg)] text-[var(--red-fg)] p-3">{report.error}</p>
        <Link href="/" className="btn">Back</Link>
      </div>
    );
  }

  const filters: Array<{ key: Filter; label: string }> = [
    { key: "all", label: `All (${claims.length})` },
    { key: "red", label: `✖ Red (${claims.filter((c) => c.colour === "red").length})` },
    { key: "amber", label: `◐ Amber (${claims.filter((c) => c.colour === "amber").length})` },
    { key: "green", label: `✔ Green (${claims.filter((c) => c.colour === "green").length})` },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-3">
        <h1 className="text-xl font-bold tracking-tight">{report.title || "Untitled draft"}</h1>
        {report.created_at && <span className="text-sm text-[var(--muted)]">{new Date(report.created_at).toLocaleString()}</span>}
      </div>
      {report.claims.some((c) => isIK(c.source?.id) || isIK(c.evidence?.source_id)) && (
        <p className="text-sm text-[var(--muted)]">
          Some sources were fetched from Indian Kanoon. <span className="font-semibold">Powered by IKanoon</span>{" "}
          (<a className="underline" href="https://indiankanoon.org" target="_blank" rel="noreferrer">indiankanoon.org</a>).
        </p>
      )}
      {report.summary && <SummaryBar summary={report.summary} />}

      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter claims">
        {filters.map((f) => (
          <button
            key={f.key}
            className={`btn !py-1 !px-3 text-sm ${filter === f.key ? "btn-primary" : ""}`}
            onClick={() => setFilter(f.key)}
            aria-pressed={filter === f.key}
          >
            {f.label}
          </button>
        ))}
      </div>

      {working && (
        <div className="card p-3 flex flex-wrap items-center gap-3 text-sm">
          <span>
            {applied.size} fix{applied.size === 1 ? "" : "es"} applied to a copy of the draft.
          </span>
          <button className="btn btn-primary !py-1" onClick={recheck} disabled={rechecking}>
            {rechecking ? "Re-checking…" : "Re-check fixed draft"}
          </button>
          <button className="btn !py-1" onClick={() => navigator.clipboard?.writeText(working)}>
            Copy fixed text
          </button>
        </div>
      )}
      {error && <p className="text-sm rounded-lg bg-[var(--red-bg)] text-[var(--red-fg)] p-3">{error}</p>}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_400px] items-start">
        <section className="card p-5 sm:p-7 min-w-0" aria-label="Draft with highlighted claims">
          <DraftViewer text={report.input_text} claims={claims} selectedId={selected} onSelect={select} visible={visible} />
        </section>

        <aside className="space-y-4 lg:sticky lg:top-4">
          <div className="card p-5">
            {current ? (
              <ClaimPanel claim={current} onApplyFix={onApplyFix} applied={applied.has(current.id)} />
            ) : (
              <p className="text-[var(--muted)]">
                {claims.length ? "Click a highlight to see its evidence." : "No checkable legal claims were found in this draft."}
              </p>
            )}
          </div>
          {listed.length > 0 && (
            <div className="card p-2 max-h-80 overflow-auto">
              <ul>
                {listed.map((c) => {
                  const m = VERDICT_META[c.verdict];
                  return (
                    <li key={c.id}>
                      <button
                        onClick={() => select(c.id)}
                        className={`w-full text-left rounded-md px-2 py-1.5 text-sm flex gap-2 hover:bg-[var(--panel-2)] ${selected === c.id ? "bg-[var(--panel-2)]" : ""}`}
                      >
                        <span className={`font-bold ${COLOUR_CLASS[c.colour].text}`} aria-label={m.label}>{m.icon}</span>
                        <span className="truncate">{c.text}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
