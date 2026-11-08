"use client";

import { ikUrl } from "@/lib/indiankanoon";
import type { Claim } from "@/lib/types";
import { COLOUR_CLASS, VERDICT_META } from "@/lib/verdicts";
import ConfidenceBar from "./ConfidenceBar";
import QuoteDiff from "./QuoteDiff";

const CITATION_STATUS: Record<string, { label: string; cls: string }> = {
  found: { label: "found ✔", cls: "chip-green" },
  not_found: { label: "not found in the source database", cls: "chip-red" },
  ambiguous: { label: "ambiguous", cls: "chip-amber" },
  unverified: { label: "could not be verified online", cls: "chip-amber" },
  none: { label: "no citation", cls: "chip-grey" },
};

function fixLabel(c: Claim): string | null {
  if (!c.fix) return null;
  if (c.fix.kind === "replace_quote") return "Replace with exact quote";
  if (c.fix.kind === "replace_citation") return `Replace citation with ${c.fix.citation}`;
  return null;
}

export default function ClaimPanel({ claim, onApplyFix, applied }: { claim: Claim; onApplyFix: (c: Claim) => void; applied: boolean }) {
  const meta = VERDICT_META[claim.verdict];
  const status = CITATION_STATUS[claim.citation_status ?? "none"] ?? CITATION_STATUS.none;
  const label = fixLabel(claim);
  const probs = claim.support_probs;

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <span className={`chip ${COLOUR_CLASS[meta.colour].chip} text-sm`}>
          <span aria-hidden>{meta.icon}</span> {meta.label.toUpperCase()}
        </span>
        <p className="text-[0.95rem] leading-relaxed">{claim.reason}</p>
      </div>

      {claim.claim_type !== "fact" && <ConfidenceBar value={claim.confidence} colour={claim.colour} />}

      {probs && (
        <dl className="grid grid-cols-3 gap-2 text-center text-xs">
          {(["supported", "contradicted", "not_enough_info"] as const).map((k) => (
            <div key={k} className="rounded-md bg-[var(--panel-2)] py-1.5">
              <dt className="text-[var(--muted)]">{k.replaceAll("_", " ")}</dt>
              <dd className="font-semibold tabular-nums">{Math.round(probs[k] * 100)}%</dd>
            </div>
          ))}
        </dl>
      )}

      <div className="space-y-1 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold">Citation</span>
          <span className={`chip ${status.cls}`}>{status.label}</span>
        </div>
        {(claim.citation_raw || claim.case_name) && (
          <p className="text-[var(--muted)]">
            Draft cites: {[claim.case_name, claim.citation_raw].filter(Boolean).join(", ")}
          </p>
        )}
        {claim.source && (
          <p>
            Source: <span className="font-medium">{claim.source.title}</span>
            {claim.source.citations.length > 0 && <span className="text-[var(--muted)]"> · {claim.source.citations.join("; ")}</span>}
            {ikUrl(claim.source.id, claim.source.title) && (
              <>
                {" · "}
                <a className="underline" href={ikUrl(claim.source.id, claim.source.title)!} target="_blank" rel="noreferrer">
                  view on Indian Kanoon
                </a>
              </>
            )}
          </p>
        )}
      </div>

      {claim.quote_text && claim.quote_diff && claim.quote_diff.length > 0 && (
        <QuoteDiff diff={claim.quote_diff} score={claim.quote_score} critical={claim.quote_critical} />
      )}
      {claim.quote_text && (!claim.quote_diff || claim.quote_diff.length === 0) && (
        <p className="text-sm text-[var(--muted)]">The quote could not be checked: no source text to compare against.</p>
      )}

      {claim.evidence && (
        <details className="rounded-lg border border-[var(--border)] p-3 text-sm" open={claim.colour === "red"}>
          <summary className="cursor-pointer font-semibold">
            Evidence: {claim.evidence.source_title}
            {claim.evidence.para && <>, para/section {claim.evidence.para}</>}
            {claim.evidence.page_start && <>, p. {claim.evidence.page_start}</>}
          </summary>
          <p className="mt-2 leading-relaxed whitespace-pre-wrap">{claim.evidence.text}</p>
        </details>
      )}

      {claim.fix?.kind === "replace_citation" && claim.fix.note && (
        <p className="text-sm rounded-lg bg-[var(--panel-2)] p-3">{claim.fix.note}</p>
      )}
      {claim.fix?.kind === "remove_claim" && (
        <p className="text-sm rounded-lg bg-[var(--red-bg)] text-[var(--red-fg)] p-3">
          Suggested: remove this claim, or find a real authority for it.
        </p>
      )}
      {claim.fix?.kind === "add_authority" && (
        <p className="text-sm rounded-lg bg-[var(--panel-2)] p-3">Suggested: add or check an authority for this claim.</p>
      )}
      {label && (
        <button className="btn btn-primary w-full" onClick={() => onApplyFix(claim)} disabled={applied}>
          {applied ? "Fix applied ✔" : label}
        </button>
      )}

      <p className="text-xs text-[var(--muted)]">
        {claim.claim_type} claim · characters {claim.char_start}–{claim.char_end}
      </p>
    </div>
  );
}
