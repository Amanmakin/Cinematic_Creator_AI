"use client";

export default function BudgetIndicator() {
  return (
    <div className="flex flex-col gap-1 opacity-40">
      <label className="text-xs font-medium text-slate-400 uppercase tracking-wide">Budget (Plan3)</label>
      <div className="h-1.5 bg-border rounded-full overflow-hidden">
        <div className="h-full w-0 bg-accent rounded-full" />
      </div>
      <p className="text-[10px] text-slate-600">Visual generation budget — available in Plan3</p>
    </div>
  );
}
