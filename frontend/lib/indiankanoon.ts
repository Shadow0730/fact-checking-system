// Sources fetched from Indian Kanoon have ids "ik-<docid>" (judgments) or "ik-act-<slug>" (statute sections).
export const isIK = (sourceId: string | null | undefined) => Boolean(sourceId && sourceId.startsWith("ik-"));

export function ikUrl(sourceId: string, title: string): string | null {
  const m = /^ik-(\d+)$/.exec(sourceId);
  if (m) return `https://indiankanoon.org/doc/${m[1]}/`;
  if (sourceId.startsWith("ik-act-")) return `https://indiankanoon.org/search/?formInput=${encodeURIComponent(title)}`;
  return null;
}
