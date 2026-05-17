"use client";

import { useProjectStore } from "@/state/projectStore";

const STATUS_COLOR: Record<string, string> = {
  idle: "bg-slate-600",
  intent_validated: "bg-blue-500",
  awaiting_human_approval: "bg-yellow-500",
  speculative_batching: "bg-purple-500",
  semantic_lock_applied: "bg-cyan-500",
  scene_graph_generated: "bg-indigo-500",
  physical_validation_failed: "bg-red-500",
  completed: "bg-green-500",
  failed: "bg-red-700",
};

export default function StateTimeline() {
  const { timeline, forkTo } = useProjectStore();

  if (timeline.length === 0) {
    return (
      <div className="text-xs text-slate-600 italic">No state events yet.</div>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-slate-400 uppercase tracking-wide">Timeline</label>
      <ol className="flex flex-col gap-1 max-h-52 overflow-y-auto pr-1">
        {timeline.map((entry, i) => (
          <li
            key={entry.checkpoint_id}
            className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer hover:text-white group"
            onClick={() => forkTo(entry.checkpoint_id)}
            title="Click to fork from this checkpoint"
          >
            <span className={`w-2 h-2 rounded-full flex-shrink-0 ${STATUS_COLOR[entry.execution_status] ?? "bg-slate-500"}`} />
            <span className="flex-1 truncate">{entry.execution_status}</span>
            <span className="text-slate-600 group-hover:text-slate-400 text-[10px]">
              {new Date(entry.timestamp).toLocaleTimeString()}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
