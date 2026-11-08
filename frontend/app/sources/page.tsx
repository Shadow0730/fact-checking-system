"use client";

import { useEffect, useState } from "react";
import { listSources, uploadSource } from "@/lib/api";
import type { SourceMeta, SourceOut } from "@/lib/types";

const EMPTY = { id: "", title: "", doc_type: "judgment" as SourceMeta["doc_type"], court: "", year: "", citations: "", aliases: "" };

export default function SourcesPage() {
  const [sources, setSources] = useState<SourceOut[] | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const load = () => listSources().then(setSources).catch((e) => setMsg({ ok: false, text: e.message }));
  useEffect(() => {
    load();
  }, []);

  const list = (s: string) => s.split(/[;\n]/).map((x) => x.trim()).filter(Boolean);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return setMsg({ ok: false, text: "Choose a file." });
    setBusy(true);
    setMsg(null);
    try {
      const meta: SourceMeta = {
        id: form.id.trim(),
        title: form.title.trim(),
        doc_type: form.doc_type,
        court: form.court.trim() || null,
        year: form.year ? Number(form.year) : null,
        citations: list(form.citations),
        aliases: list(form.aliases),
      };
      const r = await uploadSource(file, meta);
      setMsg({ ok: true, text: `Ingested ${r.id}: ${r.chunks} passages.` });
      setForm(EMPTY);
      setFile(null);
      load();
    } catch (err) {
      setMsg({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  const field = (key: keyof typeof EMPTY, label: string, placeholder = "", required = false) => (
    <label className="block text-sm">
      <span className="text-[var(--muted)]">{label}</span>
      <input
        className="input mt-1"
        value={form[key]}
        placeholder={placeholder}
        required={required}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
      />
    </label>
  );

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
      <section className="space-y-3 min-w-0">
        <h1 className="text-2xl font-bold tracking-tight">Source database</h1>
        <p className="text-[var(--muted)] text-sm">
          The checker can only verify what is in here. &quot;Not found&quot; means not in this database, not proven fake.
        </p>
        <div className="card overflow-x-auto">
          <table className="data">
            <thead>
              <tr>
                <th>Title</th>
                <th>Type</th>
                <th>Court</th>
                <th className="num">Year</th>
                <th>Citations</th>
                <th className="num">Passages</th>
              </tr>
            </thead>
            <tbody>
              {sources?.map((s) => (
                <tr key={s.id}>
                  <td>
                    <div className="font-medium">{s.title}</div>
                    <div className="text-xs text-[var(--muted)]">{s.id}</div>
                  </td>
                  <td>{s.doc_type}</td>
                  <td>{s.court ?? "–"}</td>
                  <td className="num">{s.year ?? "–"}</td>
                  <td className="text-sm">{s.citations.join("; ") || "–"}</td>
                  <td className="num">{s.chunks}</td>
                </tr>
              ))}
              {sources?.length === 0 && (
                <tr>
                  <td colSpan={6} className="text-[var(--muted)]">
                    No sources yet. Run <code>uv run python scripts/ingest_corpus.py</code> or upload one.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <aside>
        <form className="card p-5 space-y-3" onSubmit={submit}>
          <h2 className="font-semibold">Add a source</h2>
          {field("id", "ID", "e.g. sampelly-2016", true)}
          {field("title", "Title", "X v. Y", true)}
          <label className="block text-sm">
            <span className="text-[var(--muted)]">Type</span>
            <select
              className="input mt-1"
              value={form.doc_type}
              onChange={(e) => setForm({ ...form, doc_type: e.target.value as SourceMeta["doc_type"] })}
            >
              <option value="judgment">judgment</option>
              <option value="statute">statute</option>
              <option value="rules">rules</option>
              <option value="circular">circular</option>
            </select>
          </label>
          {field("court", "Court", "Supreme Court of India")}
          {field("year", "Year", "2016")}
          {field("citations", "Citations (separate with ;)", "(2016) 10 SCC 458")}
          {field("aliases", "Other names (separate with ;)", "Sampelly v. IREDA")}
          <label className="block text-sm">
            <span className="text-[var(--muted)]">File (.pdf, .docx, .txt)</span>
            <input
              type="file"
              accept=".pdf,.docx,.txt"
              className="input mt-1"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <button className="btn btn-primary w-full" disabled={busy}>
            {busy ? "Ingesting…" : "Upload and ingest"}
          </button>
          {msg && (
            <p className={`text-sm rounded-lg p-2 ${msg.ok ? "bg-[var(--green-bg)] text-[var(--green-fg)]" : "bg-[var(--red-bg)] text-[var(--red-fg)]"}`}>
              {msg.text}
            </p>
          )}
        </form>
      </aside>
    </div>
  );
}
