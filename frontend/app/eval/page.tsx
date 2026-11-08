"use client";

import { useEffect, useState } from "react";
import CalibrationChart from "@/components/CalibrationChart";
import { getEvalLatest } from "@/lib/api";
import type { EvalLatest, Metrics } from "@/lib/types";

const pct = (v: number | null | undefined) => (v === null || v === undefined ? "–" : `${(v * 100).toFixed(1)}%`);
const num = (v: number | null | undefined, d = 3) => (v === null || v === undefined ? "–" : v.toFixed(d));

const ERROR_LABELS: Record<string, string> = {
  fabricated_citation: "Fabricated citations caught",
  misquote: "Misquotes caught",
  contradicted: "Contradictions caught",
  wrong_citation: "Wrong citations caught",
};

export default function EvalPage() {
  const [dataset, setDataset] = useState<"dev" | "test">("test");
  const [data, setData] = useState<EvalLatest | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    getEvalLatest(dataset).then(setData).catch((e) => setError(e.message));
  }, [dataset]);

  const p = data?.pipeline?.metrics;
  const b = data?.baseline?.metrics;
  const offline = Boolean(data?.pipeline?.config?.offline_mode);

  const rows: Array<[string, (m: Metrics) => string]> = [
    ["Claims evaluated", (m) => String(m.n)],
    ["Precision (flagged that were bad)", (m) => pct(m.precision)],
    ["Recall (bad that were flagged)", (m) => pct(m.recall)],
    ["F0.5", (m) => num(m.f05)],
    ...Object.keys(ERROR_LABELS).map(
      (k) => [ERROR_LABELS[k], (m: Metrics) => (m.catch_rate[k] ? `${pct(m.catch_rate[k].rate)} (${m.catch_rate[k].caught}/${m.catch_rate[k].n})` : "–")] as [string, (m: Metrics) => string],
    ),
    ["Abstention rate", (m) => pct(m.abstention_rate)],
    ["Out-of-corpus claims abstained on", (m) => pct(m.nei_abstained)],
    ["Expected calibration error (lower is better)", (m) => num(m.ece)],
    ["Auto-verified at p ≥ 0.9 (share · error rate)", (m) => `${pct(m.coverage_at_090.share)} · ${pct(m.coverage_at_090.error_rate)}`],
    ["Median seconds per claim", (m) => num(m.median_seconds_per_claim, 2)],
    ["Cost per claim (₹)", (m) => (m.cost_inr_per_claim !== undefined ? num(m.cost_inr_per_claim, 4) : "–")],
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold tracking-tight">Evaluation</h1>
        <div className="flex gap-2 ml-auto" role="group" aria-label="Dataset">
          {(["test", "dev"] as const).map((d) => (
            <button key={d} className={`btn !py-1 ${dataset === d ? "btn-primary" : ""}`} onClick={() => setDataset(d)} aria-pressed={dataset === d}>
              {d}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="rounded-lg bg-[var(--red-bg)] text-[var(--red-fg)] p-3">{error}</p>}
      {data && !p && (
        <div className="card p-5 text-[var(--muted)]">
          No evaluation run for <b>{dataset}</b> yet. Run <code>uv run python scripts/run_eval.py --dataset {dataset} --with-baseline</code>.
        </div>
      )}
      {offline && (
        <p className="rounded-lg bg-[var(--amber-bg)] text-[var(--amber-fg)] p-3 text-sm">
          These numbers come from OFFLINE_MODE heuristics, not Sarvam. They are not meaningful; re-run with an API key.
        </p>
      )}

      {p && (
        <>
          <section className="card overflow-x-auto">
            <table className="data">
              <thead>
                <tr>
                  <th>Metric</th>
                  <th className="num">Pipeline (Prism + deterministic checks)</th>
                  <th className="num">Baseline (LLM self-check)</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(([label, f]) => (
                  <tr key={label}>
                    <td>{label}</td>
                    <td className="num font-semibold">{f(p)}</td>
                    <td className="num">{b ? f(b) : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="card p-5 space-y-2">
            <h2 className="font-semibold">Calibration</h2>
            <p className="text-sm text-[var(--muted)]">
              For each confidence bin: how often the top answer was actually right. A well-calibrated model sits on the diagonal.
            </p>
            <CalibrationChart pipeline={p.calibration} baseline={b?.calibration} />
          </section>

          <section className="card overflow-x-auto">
            <h2 className="font-semibold px-4 pt-4">Auto-verify threshold trade-off (pipeline)</h2>
            <table className="data">
              <thead>
                <tr>
                  <th className="num">p(supported) ≥</th>
                  <th className="num">Claims auto-verified</th>
                  <th className="num">Share</th>
                  <th className="num">Error rate among them</th>
                </tr>
              </thead>
              <tbody>
                {p.threshold_table.map((t) => (
                  <tr key={t.threshold}>
                    <td className="num">{t.threshold.toFixed(2)}</td>
                    <td className="num">{t.auto_verified}</td>
                    <td className="num">{pct(t.share)}</td>
                    <td className="num">{pct(t.error_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <p className="text-xs text-[var(--muted)]">
            Pipeline run {new Date(data!.pipeline!.created_at).toLocaleString()}
            {data?.baseline && <> · baseline run {new Date(data.baseline.created_at).toLocaleString()}</>}. Flagged = red or amber “weak”.
            Test claims are synthetic, generated from the corpus; report how many were human-checked.
          </p>
        </>
      )}
    </div>
  );
}
