"use client";

import { useEffect, useState } from "react";
import { getHealth } from "@/lib/api";
import type { Health } from "@/lib/types";

// Keeps polling: the backend can take minutes on first start (installing / downloading the embedding model).
export default function HealthBadge() {
  const [h, setH] = useState<Health | null>(null);
  const [down, setDown] = useState(false);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = () => {
      getHealth()
        .then((r) => {
          if (!alive) return;
          setH(r);
          setDown(false);
          timer = setTimeout(poll, 30000);
        })
        .catch(() => {
          if (!alive) return;
          setDown(true);
          timer = setTimeout(poll, 3000);
        });
    };
    poll();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, []);

  if (down)
    return (
      <span className="chip chip-red" title="Retrying every 3 s. On first start the backend may still be loading the embedding model.">
        backend not reachable · retrying…
      </span>
    );
  if (!h) return null;
  if (h.db !== "ok" && h.db !== "memory") return <span className="chip chip-red">database unreachable</span>;
  return (
    <span className="flex items-center gap-2">
      {h.offline_mode && <span className="chip chip-amber">offline mode</span>}
      {h.online_lookup && <span className="chip chip-green" title="Citations not in the corpus are looked up on Indian Kanoon">Indian Kanoon on</span>}
      <span className="chip chip-grey" title={`${h.embedding_model}`}>
        {h.sources} sources · {h.chunks} passages
      </span>
    </span>
  );
}
