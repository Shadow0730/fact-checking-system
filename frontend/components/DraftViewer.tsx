"use client";

import type { Claim, Colour } from "@/lib/types";
import { COLOUR_CLASS, SEVERITY, VERDICT_META } from "@/lib/verdicts";

type Segment = { start: number; end: number; claim: Claim | null };

/** Split the text at every claim boundary; where claims overlap, the most severe colour wins. */
function segments(text: string, claims: Claim[]): Segment[] {
  const cuts = new Set<number>([0, text.length]);
  for (const c of claims) {
    cuts.add(Math.max(0, Math.min(text.length, c.char_start)));
    cuts.add(Math.max(0, Math.min(text.length, c.char_end)));
  }
  const points = [...cuts].sort((a, b) => a - b);
  const out: Segment[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const [s, e] = [points[i], points[i + 1]];
    if (s === e) continue;
    let best: Claim | null = null;
    for (const c of claims) {
      if (c.char_start <= s && c.char_end >= e && (!best || SEVERITY[c.colour] > SEVERITY[best.colour])) best = c;
    }
    out.push({ start: s, end: e, claim: best });
  }
  return out;
}

export default function DraftViewer({
  text,
  claims,
  selectedId,
  onSelect,
  visible,
}: {
  text: string;
  claims: Claim[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  visible: (c: Claim) => boolean;
}) {
  const firstSegmentOf = new Map<string, number>();
  const segs = segments(text, claims);
  segs.forEach((s, i) => {
    if (s.claim && !firstSegmentOf.has(s.claim.id)) firstSegmentOf.set(s.claim.id, i);
  });

  return (
    <div className="draft text-[1.02rem]">
      {segs.map((s, i) => {
        const chunk = text.slice(s.start, s.end);
        if (!s.claim) return <span key={i}>{chunk}</span>;
        const c = s.claim;
        const meta = VERDICT_META[c.verdict];
        const colour: Colour = c.colour;
        const dim = !visible(c);
        const showIcon = firstSegmentOf.get(c.id) === i;
        return (
          <mark
            key={i}
            id={showIcon ? `claim-${c.id}` : undefined}
            className={`${COLOUR_CLASS[colour].mark} ${selectedId === c.id ? "selected" : ""} ${dim ? "dim" : ""}`}
            onClick={() => onSelect(c.id)}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onSelect(c.id))}
            tabIndex={showIcon ? 0 : -1}
            role="button"
            aria-label={showIcon ? `${meta.label}: ${c.text.slice(0, 80)}` : undefined}
            title={meta.label}
          >
            {showIcon && (
              <span aria-hidden className={`text-xs font-bold mr-0.5 ${COLOUR_CLASS[colour].text}`}>
                {meta.icon}
              </span>
            )}
            {chunk}
          </mark>
        );
      })}
    </div>
  );
}
