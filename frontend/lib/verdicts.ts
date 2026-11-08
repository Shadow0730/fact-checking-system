import type { Colour, Verdict } from "./types";

// Colour is never the only signal: every verdict also has an icon and a text label.
export const VERDICT_META: Record<Verdict, { label: string; icon: string; colour: Colour }> = {
  verified: { label: "Verified", icon: "✔", colour: "green" },
  weak: { label: "Weak support", icon: "◐", colour: "amber" },
  insufficient: { label: "Insufficient sources", icon: "?", colour: "amber" },
  misquote: { label: "Misquote", icon: "✖", colour: "red" },
  contradicted: { label: "Contradicted", icon: "✖", colour: "red" },
  fabricated: { label: "Possibly fabricated", icon: "✖", colour: "red" },
  not_legal: { label: "Not a legal claim", icon: "–", colour: "grey" },
};

export const SEVERITY: Record<Colour, number> = { red: 3, amber: 2, green: 1, grey: 0 };

export const COLOUR_CLASS: Record<Colour, { mark: string; chip: string; text: string }> = {
  green: { mark: "mark-green", chip: "chip-green", text: "text-[var(--green-fg)]" },
  amber: { mark: "mark-amber", chip: "chip-amber", text: "text-[var(--amber-fg)]" },
  red: { mark: "mark-red", chip: "chip-red", text: "text-[var(--red-fg)]" },
  grey: { mark: "mark-grey", chip: "chip-grey", text: "text-[var(--muted)]" },
};
