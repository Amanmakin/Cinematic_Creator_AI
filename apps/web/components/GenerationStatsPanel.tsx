"use client";

import { useEffect, useState } from "react";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface GenerationStats {
  total_generations: number;
  local_count: number;
  replicate_count: number;
  fallback_count: number;
  total_cost_usd: number;
  local_avg_time_sec: number | null;
  replicate_avg_time_sec: number | null;
}

async function fetchStats(projectId: string): Promise<GenerationStats> {
  const res = await fetch(`${BASE}/projects/${projectId}/generation-stats`);
  if (!res.ok) throw new Error(`fetchStats failed: ${res.status}`);
  return res.json();
}

interface Props {
  projectId: string;
}

export function GenerationStatsPanel({ projectId }: Props) {
  const [stats, setStats] = useState<GenerationStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchStats(projectId)
      .then(setStats)
      .catch((e) => setError(e.message));
  }, [projectId]);

  if (error) return <p className="text-xs text-red-500">{error}</p>;
  if (!stats) return <p className="text-sm text-gray-500">Loading stats…</p>;
  if (stats.total_generations === 0) {
    return <p className="text-sm text-gray-400">No generations yet for this project.</p>;
  }

  const localPct =
    stats.total_generations > 0
      ? Math.round((stats.local_count / stats.total_generations) * 100)
      : 0;

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 space-y-3">
      <h3 className="font-semibold text-gray-800">Generation Stats</h3>

      <div className="grid grid-cols-2 gap-3 text-sm">
        <Stat label="Total generations" value={String(stats.total_generations)} />
        <Stat
          label="Local / Cloud"
          value={`${stats.local_count} / ${stats.replicate_count}`}
        />
        <Stat label="Local share" value={`${localPct}%`} />
        <Stat label="Fallbacks triggered" value={String(stats.fallback_count)} />
        <Stat
          label="Total cost"
          value={`$${stats.total_cost_usd.toFixed(4)}`}
          highlight={stats.total_cost_usd > 0}
        />
        <Stat
          label="Local avg time"
          value={stats.local_avg_time_sec != null ? `${stats.local_avg_time_sec}s` : "—"}
        />
        <Stat
          label="Cloud avg time"
          value={
            stats.replicate_avg_time_sec != null ? `${stats.replicate_avg_time_sec}s` : "—"
          }
        />
      </div>

      {stats.total_generations > 0 && (
        <div className="mt-2">
          <div className="text-xs text-gray-500 mb-1">Local vs. cloud split</div>
          <div className="h-2 rounded-full bg-gray-200 overflow-hidden">
            <div
              className="h-full bg-emerald-500 transition-all"
              style={{ width: `${localPct}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-gray-400 mt-0.5">
            <span>Local (free)</span>
            <span>Replicate ($)</span>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div>
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`font-medium ${highlight ? "text-amber-600" : "text-gray-800"}`}>{value}</p>
    </div>
  );
}
