import type { Summary, Verdict } from "@/lib/types";
import { COLOUR_CLASS, VERDICT_META } from "@/lib/verdicts";

const ORDER: Verdict[] = ["verified", "weak", "insufficient", "misquote", "contradicted", "fabricated", "not_legal"];

export default function SummaryBar({ summary }: { summary: Summary }) {
  return (
    <div className="card px-4 py-3 flex flex-wrap items-center gap-2">
      {ORDER.filter((v) => summary[v] > 0 || v === "verified").map((v) => {
        const m = VERDICT_META[v];
        return (
          <span key={v} className={`chip ${COLOUR_CLASS[m.colour].chip}`}>
            <span aria-hidden>{m.icon}</span>
            {summary[v]} {m.label.toLowerCase()}
          </span>
        );
      })}
      <span className="ml-auto text-sm text-[var(--muted)] tabular-nums">
        {summary.claims} claims · {summary.seconds.toFixed(1)} s
        {summary.prism_input_tokens > 0 && <> · ₹{summary.cost_inr.toFixed(2)}</>}
      </span>
      {summary.offline_mode && (
        <span className="chip chip-amber w-full sm:w-auto justify-center">
          Offline mode: heuristic results, not meaningful
        </span>
      )}
    </div>
  );
}
