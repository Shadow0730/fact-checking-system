import type {
  CheckListItem,
  EvalLatest,
  Health,
  Report,
  SourceMeta,
  SourceOut,
} from "./types";

export const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new ApiError("NETWORK", `Cannot reach the backend at ${BASE}. Is it running?`, 0);
  }
  if (!r.ok) {
    let code = "HTTP_" + r.status;
    let message = r.statusText;
    try {
      const body = await r.json();
      code = body.error?.code ?? code;
      message = body.error?.message ?? message;
    } catch {
      /* not JSON */
    }
    throw new ApiError(code, message, r.status);
  }
  return r.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const getHealth = () => call<Health>("/health");

export const runCheck = (text: string, title?: string) => call<Report>("/api/checks", json({ text, title }));

export function runCheckFile(file: File, title?: string): Promise<Report> {
  const fd = new FormData();
  fd.append("file", file);
  if (title) fd.append("title", title);
  return call<Report>("/api/checks", { method: "POST", body: fd });
}

export const getCheck = (id: string) => call<Report>(`/api/checks/${id}`);
export const listChecks = () => call<CheckListItem[]>("/api/checks");

export const applyFix = (checkId: string, claimId: string) =>
  call<{ text: string }>(`/api/checks/${checkId}/claims/${claimId}/apply-fix`, { method: "POST" });

export const listSources = () => call<SourceOut[]>("/api/sources");

export function uploadSource(file: File, meta: SourceMeta) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("meta", JSON.stringify(meta));
  return call<{ id: string; chunks: number }>("/api/sources", { method: "POST", body: fd });
}

export const getEvalLatest = (dataset: "dev" | "test") => call<EvalLatest>(`/api/eval/latest?dataset=${dataset}`);

export const getDemoDrafts = () => call<Array<{ name: string; text: string }>>("/api/demo-drafts");
