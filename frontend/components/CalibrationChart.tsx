"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { CalibrationBin } from "@/lib/types";

const pts = (bins: CalibrationBin[] | undefined) =>
  (bins ?? []).map((b) => ({ x: b.mean_confidence, y: b.accuracy, n: b.n }));

export default function CalibrationChart({ pipeline, baseline }: { pipeline?: CalibrationBin[]; baseline?: CalibrationBin[] }) {
  return (
    <div className="h-80 w-full" role="img" aria-label="Calibration chart: predicted confidence against actual accuracy">
      <ResponsiveContainer>
        <LineChart margin={{ top: 10, right: 20, bottom: 20, left: 0 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
          <XAxis
            type="number"
            dataKey="x"
            domain={[0, 1]}
            ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]}
            tickFormatter={(v) => `${Math.round(v * 100)}%`}
            stroke="var(--muted)"
            label={{ value: "predicted confidence", position: "insideBottom", offset: -10, fill: "var(--muted)" }}
          />
          <YAxis
            type="number"
            domain={[0, 1]}
            ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]}
            tickFormatter={(v) => `${Math.round(v * 100)}%`}
            stroke="var(--muted)"
          />
          <Tooltip
            formatter={(v: number, name: string) => [`${Math.round(v * 100)}%`, name]}
            labelFormatter={(v) => `confidence ${Math.round(Number(v) * 100)}%`}
            contentStyle={{ background: "var(--panel)", border: "1px solid var(--border)", color: "var(--fg)" }}
          />
          <Legend verticalAlign="top" height={30} />
          <Line
            name="perfect calibration"
            data={[{ x: 0, y: 0 }, { x: 1, y: 1 }]}
            dataKey="y"
            stroke="var(--muted)"
            strokeDasharray="5 5"
            dot={false}
            isAnimationActive={false}
          />
          <Line name="Pipeline (Prism)" data={pts(pipeline)} dataKey="y" stroke="var(--accent)" strokeWidth={2.5} isAnimationActive={false} />
          {baseline && baseline.length > 0 && (
            <Line name="Baseline (LLM self-report)" data={pts(baseline)} dataKey="y" stroke="var(--red-line)" strokeWidth={2} isAnimationActive={false} />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
