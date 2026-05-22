"use client";

import { useProjectStore } from "@/state/projectStore";
import type { ExecutionStage } from "@/lib/types/agentState";

interface PhaseInfo {
  label: string;
  emoji: string;
  color: string; // Tailwind text color
  bg: string;   // Tailwind bg color (subtle)
  dot: string;  // Tailwind bg color for pulsing dot
}

const PHASE_INFO: Record<ExecutionStage, PhaseInfo> = {
  idle:                        { label: "Ready",                     emoji: "🎬", color: "text-zinc-300",   bg: "bg-zinc-800/60",   dot: "bg-zinc-400" },
  intent_validated:            { label: "Analyzing Intent",          emoji: "🧠", color: "text-indigo-300", bg: "bg-indigo-900/30", dot: "bg-indigo-400" },
  awaiting_human_approval:     { label: "Awaiting Your Review",      emoji: "👁️", color: "text-amber-300",  bg: "bg-amber-900/30",  dot: "bg-amber-400" },
  speculative_batching:        { label: "Exploring Variants",        emoji: "✨", color: "text-indigo-300", bg: "bg-indigo-900/30", dot: "bg-indigo-400" },
  semantic_lock_applied:       { label: "Locking Elements",          emoji: "🔒", color: "text-teal-300",   bg: "bg-teal-900/30",   dot: "bg-teal-400" },
  scene_graph_generated:       { label: "Scene Composed",            emoji: "🎥", color: "text-blue-300",   bg: "bg-blue-900/30",   dot: "bg-blue-400" },
  previsualization_generated:  { label: "Previsualization Ready",    emoji: "🖼️", color: "text-amber-300",  bg: "bg-amber-900/30",  dot: "bg-amber-400" },
  previsualization_approved:   { label: "Animatic Approved",         emoji: "✅", color: "text-emerald-300",bg: "bg-emerald-900/30",dot: "bg-emerald-400" },
  previsualization_feedback:   { label: "Refining Animatic",         emoji: "✏️", color: "text-indigo-300", bg: "bg-indigo-900/30", dot: "bg-indigo-400" },
  model_generated:             { label: "3D Models Ready",           emoji: "🗿", color: "text-amber-300",  bg: "bg-amber-900/30",  dot: "bg-amber-400" },
  model_approved:              { label: "Models Approved",           emoji: "✅", color: "text-emerald-300",bg: "bg-emerald-900/30",dot: "bg-emerald-400" },
  model_feedback:              { label: "Refining Models",           emoji: "🔧", color: "text-indigo-300", bg: "bg-indigo-900/30", dot: "bg-indigo-400" },
  creative_dispatching:        { label: "Dispatching Creation",      emoji: "🚀", color: "text-indigo-300", bg: "bg-indigo-900/30", dot: "bg-indigo-400" },
  visual_generating:           { label: "Synthesizing Visuals",      emoji: "🎨", color: "text-violet-300", bg: "bg-violet-900/30", dot: "bg-violet-400" },
  dsl_compiled:                { label: "Compiling Scene",           emoji: "⚙️", color: "text-blue-300",   bg: "bg-blue-900/30",   dot: "bg-blue-400" },
  gltf_assembled:              { label: "Assembling 3D Scene",       emoji: "🧩", color: "text-blue-300",   bg: "bg-blue-900/30",   dot: "bg-blue-400" },
  render_progress:             { label: "Rendering Frames",          emoji: "🎞️", color: "text-indigo-300", bg: "bg-indigo-900/30", dot: "bg-indigo-400" },
  render_completed:            { label: "Render Complete",           emoji: "🎉", color: "text-emerald-300",bg: "bg-emerald-900/30",dot: "bg-emerald-400" },
  completed:                   { label: "Complete",                  emoji: "🏆", color: "text-emerald-300",bg: "bg-emerald-900/30",dot: "bg-emerald-400" },
  budget_exceeded:             { label: "Budget Exceeded",           emoji: "💸", color: "text-orange-300", bg: "bg-orange-900/30", dot: "bg-orange-400" },
  physical_validation_failed:  { label: "Physics Violation",         emoji: "⚠️", color: "text-red-300",    bg: "bg-red-900/30",    dot: "bg-red-400" },
  dsl_validation_failed:       { label: "DSL Error",                 emoji: "🚫", color: "text-red-300",    bg: "bg-red-900/30",    dot: "bg-red-400" },
  render_timed_out:            { label: "Render Timed Out",          emoji: "⏱️", color: "text-red-300",    bg: "bg-red-900/30",    dot: "bg-red-400" },
  failed:                      { label: "Failed",                    emoji: "💥", color: "text-red-300",    bg: "bg-red-900/30",    dot: "bg-red-400" },
};

const QUIET_STAGES: ExecutionStage[] = ["idle"];

export default function PhaseStatusBar() {
  const { agentState, isRunning } = useProjectStore();

  const status = agentState?.execution_status ?? "idle";
  const info = PHASE_INFO[status] ?? PHASE_INFO.idle;

  if (QUIET_STAGES.includes(status) && !isRunning) return null;

  const isActive = isRunning || status !== "idle";
  const isError = status.includes("failed") || status === "failed" || status === "budget_exceeded" || status === "render_timed_out";
  const isWaiting = status === "awaiting_human_approval" || status === "previsualization_generated" || status === "model_generated";

  return (
    <div
      className={[
        "flex items-center gap-3 px-3 py-2.5 rounded-lg border transition-all duration-500",
        info.bg,
        isError
          ? "border-red-500/30"
          : isWaiting
            ? "border-amber-500/30"
            : "border-indigo-500/25",
      ].join(" ")}
    >
      {/* Pulsing dot */}
      <div className="relative flex-shrink-0 w-2 h-2">
        {isActive && !isError && (
          <div className={`absolute inset-0 rounded-full ${info.dot} opacity-60 animate-ping`} />
        )}
        <div className={`relative w-2 h-2 rounded-full ${info.dot} ${isError ? "animate-pulse" : ""}`} />
      </div>

      {/* Emoji */}
      <span className="text-sm leading-none select-none">{info.emoji}</span>

      {/* Label */}
      <div className="flex-1 min-w-0">
        <p className={`text-xs font-semibold tracking-wide uppercase truncate ${info.color}`}>
          {info.label}
        </p>
      </div>

      {/* Stage key badge */}
      <span
        data-testid="phase-status-badge"
        className="text-[9px] font-mono text-zinc-500 tracking-wide flex-shrink-0"
      >
        {status}
      </span>
    </div>
  );
}
