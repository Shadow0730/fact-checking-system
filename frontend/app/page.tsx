"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { getDemoDrafts, listChecks, runCheck, runCheckFile } from "@/lib/api";
import type { CheckListItem } from "@/lib/types";

const STAGES = ["Splitting the draft into sentences…", "Extracting claims…", "Resolving citations…",
  "Checking quotes against the sources…", "Judging each claim against the passages…", "Scoring…"];

export default function CheckPage() {
  const router = useRouter();
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [demoNames, setDemoNames] = useState<string[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<CheckListItem[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    listChecks().then(setRecent).catch(() => {});
    getDemoDrafts().then((d) => setDemoNames(d.map((x) => x.name))).catch(() => {});
  }, []);

  useEffect(() => {
    if (!busy) return;
    setStage(0);
    const t = setInterval(() => setStage((s) => Math.min(s + 1, STAGES.length - 1)), 2500);
    return () => clearInterval(t);
  }, [busy]);

  async function loadDemo(name: string) {
    setError(null);
    try {
      const drafts = await getDemoDrafts();
      const d = drafts.find((x) => x.name === name) ?? drafts[0];
      if (!d) return setError("No demo drafts found in eval/drafts/.");
      setText(d.text);
      setTitle(d.name);
      setFile(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      const report = file ? await runCheckFile(file, title || undefined) : await runCheck(text, title || undefined);
      router.push(`/checks/${report.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  const canSubmit = !busy && (file !== null || text.trim().length > 0);

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
      <section className="space-y-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Check a legal draft</h1>
          <p className="text-[var(--muted)] mt-1">
            Finds citations that aren&apos;t in the source database, quotes that don&apos;t match the source,
            and claims the sources don&apos;t support. It abstains when the sources don&apos;t settle a claim.
          </p>
        </div>

        <input
          className="input"
          placeholder="Title (optional)"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          aria-label="Title"
        />
        <textarea
          className="input draft min-h-[420px] text-[0.98rem]"
          placeholder="Paste your draft here…"
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setFile(null);
          }}
          disabled={file !== null}
          aria-label="Draft text"
        />

        <div className="flex flex-wrap items-center gap-3">
          <button className="btn btn-primary" onClick={submit} disabled={!canSubmit}>
            {busy ? "Checking…" : "Check draft"}
          </button>
          <select
            className="btn"
            aria-label="Load an example draft"
            disabled={busy || demoNames.length === 0}
            value=""
            onChange={(e) => e.target.value && loadDemo(e.target.value)}
          >
            <option value="">Load example draft…</option>
            {demoNames.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
          <button className="btn" onClick={() => fileInput.current?.click()} disabled={busy}>
            Upload .txt / .docx / .pdf
          </button>
          <input
            ref={fileInput}
            type="file"
            accept=".txt,.docx,.pdf"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0] ?? null;
              setFile(f);
              if (f && !title) setTitle(f.name.replace(/\.[^.]+$/, ""));
            }}
          />
          {file && (
            <span className="chip chip-grey">
              {file.name}
              <button aria-label="Remove file" onClick={() => setFile(null)} className="ml-1">✕</button>
            </span>
          )}
        </div>

        {busy && (
          <p className="text-sm text-[var(--muted)]" aria-live="polite">
            {STAGES[stage]} A 20-claim draft takes roughly 10–30 seconds.
          </p>
        )}
        {error && <p className="text-sm rounded-lg bg-[var(--red-bg)] text-[var(--red-fg)] p-3">{error}</p>}
      </section>

      <aside className="space-y-3">
        <h2 className="font-semibold">Recent checks</h2>
        {recent.length === 0 && <p className="text-sm text-[var(--muted)]">None yet.</p>}
        <ul className="space-y-2">
          {recent.map((c) => (
            <li key={c.id}>
              <Link href={`/checks/${c.id}`} className="card block p-3 hover:bg-[var(--panel-2)]">
                <div className="font-medium truncate">{c.title || "Untitled draft"}</div>
                <div className="text-xs text-[var(--muted)] mt-1">
                  {new Date(c.created_at).toLocaleString()} · {c.status}
                  {c.summary && (
                    <> · {c.summary.claims} claims, {c.summary.misquote + c.summary.contradicted + c.summary.fabricated} red</>
                  )}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
