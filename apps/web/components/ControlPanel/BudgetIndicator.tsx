"use client";

import { useEffect, useState } from "react";

interface BudgetIndicatorProps {
  projectId?: string;
}

export default function BudgetIndicator({ projectId }: BudgetIndicatorProps) {
  const [remaining, setRemaining] = useState<number | null>(null);
  const [cap, setCap] = useState(10_000);

  useEffect(() => {
    if (!projectId) return;
    const fetchBudget = async () => {
      try {
        const res = await fetch(`/api/projects/${projectId}/budget`);
        if (res.ok) {
          const data = await res.json();
          setRemaining(data.remaining ?? null);
          setCap(data.cap ?? 10_000);
        }
      } catch {
        // ignore network errors
      }
    };
    fetchBudget();
    const interval = setInterval(fetchBudget, 5000);
    return () => clearInterval(interval);
  }, [projectId]);

  const pct = remaining !== null ? Math.round((remaining / cap) * 100) : 0;
  const color =
    pct > 50 ? "bg-green-500" : pct > 20 ? "bg-yellow-400" : "bg-red-500";

  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-slate-400 uppercase tracking-wide">Budget</label>
      <div className="h-1.5 bg-border rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-[10px] text-slate-500">
        {remaining !== null
          ? `${remaining.toLocaleString()} / ${cap.toLocaleString()} tokens remaining`
          : "Loading budget…"}
      </p>
    </div>
  );
}
