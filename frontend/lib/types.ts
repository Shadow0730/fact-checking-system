// TypeScript mirrors of backend/app/schemas.py

export type Verdict =
  | "verified"
  | "weak"
  | "insufficient"
  | "misquote"
  | "contradicted"
  | "fabricated"
  | "not_legal";
export type Colour = "green" | "amber" | "red" | "grey";
export type ClaimType = "holding" | "statutory" | "quote" | "fact";

export interface SourceRef {
  id: string;
  title: string;
  citations: string[];
}

export interface Evidence {
  chunk_id: number;
  source_id: string;
  source_title: string;
  para: string | null;
  page_start: number | null;
  text: string;
}

export interface DiffOp {
  op: "equal" | "replace" | "delete" | "insert";
  draft: string;
  source: string;
}

export type Fix =
  | { kind: "replace_quote"; text: string; from?: string; chunk_id?: number }
  | {
      kind: "replace_citation";
      source_id: string;
      source_title: string;
      citation: string;
      from?: string | null;
      chunk_id?: number | null;
      note?: string;
    }
  | { kind: "remove_claim" }
  | { kind: "show_source"; chunk_id: number }
  | { kind: "add_authority" };

export interface Claim {
  id: string;
  ord: number;
  char_start: number;
  char_end: number;
  text: string;
  claim_type: ClaimType;
  citation_raw: string | null;
  citation_key: string | null;
  citation_status: "found" | "not_found" | "ambiguous" | "unverified" | "none" | null;
  case_name: string | null;
  source: SourceRef | null;
  quote_text: string | null;
  quote_score: number | null;
  quote_match: string | null;
  quote_diff: DiffOp[] | null;
  quote_critical: boolean | null;
  support_probs: Record<"supported" | "contradicted" | "not_enough_info", number> | null;
  evidence: Evidence | null;
  verdict: Verdict;
  colour: Colour;
  confidence: number | null;
  reason: string;
  fix: Fix | null;
}

export interface Summary {
  claims: number;
  verified: number;
  weak: number;
  insufficient: number;
  misquote: number;
  contradicted: number;
  fabricated: number;
  not_legal: number;
  seconds: number;
  prism_input_tokens: number;
  llm_tokens: number;
  cost_inr: number;
  offline_mode: boolean;
  online_lookups?: number;
  online_found?: number;
}

export interface Report {
  id: string;
  title: string | null;
  status: string;
  input_text: string;
  summary: Summary | null;
  error: string | null;
  created_at: string | null;
  claims: Claim[];
}

export interface CheckListItem {
  id: string;
  title: string | null;
  status: string;
  created_at: string;
  summary: Summary | null;
}

export interface SourceOut {
  id: string;
  title: string;
  doc_type: string;
  court: string | null;
  year: number | null;
  language: string;
  citations: string[];
  citation_keys: string[];
  chunks: number;
}

export interface SourceMeta {
  id: string;
  title: string;
  doc_type: "judgment" | "statute" | "rules" | "circular";
  court?: string | null;
  year?: number | null;
  language?: string;
  citations: string[];
  aliases: string[];
}

export interface Health {
  db: string;
  embedding_model: string;
  embedding_loaded: boolean;
  sources: number;
  chunks: number;
  offline_mode: boolean;
  online_lookup?: boolean;
}

export interface CalibrationBin {
  lo: number;
  hi: number;
  n: number;
  mean_confidence: number;
  accuracy: number;
}

export interface ThresholdRow {
  threshold: number;
  auto_verified: number;
  share: number;
  error_rate: number | null;
}

export interface Metrics {
  n: number;
  bad: number;
  flagged: number;
  precision: number;
  recall: number;
  f05: number;
  catch_rate: Record<string, { n: number; caught: number; red: number; rate: number }>;
  abstention_rate: number;
  nei_abstained: number | null;
  verdicts: Record<string, number>;
  calibration: CalibrationBin[];
  ece: number | null;
  coverage_at_090: ThresholdRow;
  threshold_table: ThresholdRow[];
  median_seconds_per_claim: number | null;
  cost_inr_per_claim?: number;
  sweep?: Array<{ supported: number; weak: number; contradicted: number; f05: number; precision: number; recall: number; abstention_rate: number }>;
}

export interface EvalRun {
  created_at: string;
  config: Record<string, unknown> & { offline_mode?: boolean; n?: number };
  metrics: Metrics;
}

export interface EvalLatest {
  dataset: string;
  pipeline: EvalRun | null;
  baseline: EvalRun | null;
}
