import type { Colour } from "@/lib/types";

const FILL: Record<Colour, string> = {
  green: "var(--green-line)",
  amber: "var(--amber-line)",
  red: "var(--red-line)",
  grey: "var(--grey-line)",
};

export default function ConfidenceBar({ value, colour, label = "Support" }: { value: number | null; colour: Colour; label?: string }) {
  if (value === null || value === undefined) {
    return <p className="text-sm text-[var(--muted)]">{label}: not scored</p>;
  }
  const pct = Math.round(value * 100);
  return (
    <div>
      <div className="flex justify-between text-sm mb-1">
        <span className="text-[var(--muted)]">{label} (p)</span>
        <span className="font-semibold tabular-nums">{pct}%</span>
      </div>
      <div
        className="h-2.5 w-full rounded-full bg-[var(--panel-2)] overflow-hidden"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-label={`${label} probability ${pct}%`}
      >
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: FILL[colour] }} />
      </div>
    </div>
  );
}
