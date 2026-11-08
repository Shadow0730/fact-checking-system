import type { DiffOp } from "@/lib/types";

export default function QuoteDiff({ diff, score, critical }: { diff: DiffOp[]; score: number | null; critical: boolean | null }) {
  const changed = diff.some((d) => d.op !== "equal");
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-sm">
        <span className="font-semibold">Quote check</span>
        {score !== null && <span className="text-[var(--muted)] tabular-nums">match {score.toFixed(1)}/100</span>}
        {critical && <span className="chip chip-red">meaning-changing word</span>}
        {!changed && <span className="chip chip-green">✔ exact</span>}
      </div>
      <div className="text-sm leading-relaxed rounded-lg bg-[var(--panel-2)] p-3 space-y-2">
        <p>
          <span className="text-[var(--muted)] mr-2 text-xs uppercase tracking-wide">draft</span>
          {diff.map((d, i) =>
            d.op === "equal" ? (
              <span key={i}>{d.draft} </span>
            ) : d.draft ? (
              <span key={i}>
                <span className="diff-del" aria-label={`draft has ${d.draft}`}>{d.draft}</span>{" "}
              </span>
            ) : null,
          )}
        </p>
        <p>
          <span className="text-[var(--muted)] mr-2 text-xs uppercase tracking-wide">source</span>
          {diff.map((d, i) =>
            d.op === "equal" ? (
              <span key={i}>{d.source} </span>
            ) : d.source ? (
              <span key={i}>
                <span className="diff-ins" aria-label={`source has ${d.source}`}>{d.source}</span>{" "}
              </span>
            ) : null,
          )}
        </p>
      </div>
    </div>
  );
}
