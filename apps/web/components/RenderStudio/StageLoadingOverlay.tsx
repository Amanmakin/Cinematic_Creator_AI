"use client";

import { useProjectStore } from "@/state/projectStore";
import type { ExecutionStage } from "@/lib/types/agentState";

interface StageConfig {
  label: string;
  description: string;
  type: "progress" | "waiting" | "success" | "error";
  /** 0-based index in the main pipeline for progress bar (null = not in pipeline) */
  step: number | null;
}

const PIPELINE_STEPS = 10; // total steps shown in the progress stepper

const STAGE_CONFIG: Record<ExecutionStage, StageConfig> = {
  idle: {
    label: "Ready",
    description: "Waiting for your prompt",
    type: "success",
    step: null,
  },
  intent_validated: {
    label: "Validating Intent",
    description: "Parsing and understanding your creative prompt",
    type: "progress",
    step: 0,
  },
  awaiting_human_approval: {
    label: "Awaiting Your Approval",
    description: "Review the proposed scene before we continue",
    type: "waiting",
    step: 1,
  },
  speculative_batching: {
    label: "Generating Variants",
    description: "Exploring multiple interpretations in parallel",
    type: "progress",
    step: 2,
  },
  semantic_lock_applied: {
    label: "Applying Semantic Locks",
    description: "Pinning your approved elements before generation",
    type: "progress",
    step: 3,
  },
  scene_graph_generated: {
    label: "Scene Graph Ready",
    description: "3D scene structure has been composed",
    type: "progress",
    step: 4,
  },
  creative_dispatching: {
    label: "Dispatching Creative Work",
    description: "Routing assets to local and cloud generators",
    type: "progress",
    step: 5,
  },
  visual_generating: {
    label: "Generating Visuals",
    description: "Synthesising images and layer assets",
    type: "progress",
    step: 6,
  },
  dsl_compiled: {
    label: "Compiling Scene DSL",
    description: "Translating scene description into Blender instructions",
    type: "progress",
    step: 7,
  },
  gltf_assembled: {
    label: "Assembling 3D Scene",
    description: "Merging layers and geometry into glTF format",
    type: "progress",
    step: 8,
  },
  render_progress: {
    label: "Rendering",
    description: "Blender is processing frames headlessly",
    type: "progress",
    step: 9,
  },
  render_completed: {
    label: "Render Complete",
    description: "All frames rendered, compositing final output",
    type: "success",
    step: null,
  },
  completed: {
    label: "Completed",
    description: "Your cinematic scene is ready",
    type: "success",
    step: null,
  },
  // --- error states ---
  budget_exceeded: {
    label: "Budget Exceeded",
    description: "Generation cost limit reached — adjust settings and retry",
    type: "error",
    step: null,
  },
  physical_validation_failed: {
    label: "Physical Validation Failed",
    description: "Scene geometry has constraint violations",
    type: "error",
    step: null,
  },
  dsl_validation_failed: {
    label: "DSL Validation Failed",
    description: "Scene description could not be compiled",
    type: "error",
    step: null,
  },
  render_timed_out: {
    label: "Render Timed Out",
    description: "The render process exceeded the allowed duration",
    type: "error",
    step: null,
  },
  failed: {
    label: "Failed",
    description: "An unexpected error occurred",
    type: "error",
    step: null,
  },
};

const HIDDEN_STAGES: ExecutionStage[] = ["idle", "completed", "render_completed"];

function Spinner() {
  return (
    <div className="relative flex items-center justify-center w-14 h-14">
      <div className="absolute inset-0 rounded-full border-2 border-indigo-500/20" />
      <div className="absolute inset-0 rounded-full border-t-2 border-indigo-400 animate-spin" />
      <div className="absolute inset-1 rounded-full border-t border-indigo-300/40 animate-spin [animation-duration:1.5s] [animation-direction:reverse]" />
      <div className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse" />
    </div>
  );
}

function WaitingPulse() {
  return (
    <div className="relative flex items-center justify-center w-14 h-14">
      <div className="absolute inset-0 rounded-full bg-amber-500/10 animate-ping [animation-duration:2s]" />
      <div className="absolute inset-2 rounded-full bg-amber-500/20 animate-ping [animation-duration:2s] [animation-delay:0.5s]" />
      <div className="w-5 h-5 rounded-full bg-amber-400 animate-pulse" />
    </div>
  );
}

function ErrorIcon() {
  return (
    <div className="relative flex items-center justify-center w-14 h-14">
      <div className="absolute inset-0 rounded-full bg-red-500/10" />
      <svg className="w-8 h-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 4h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      </svg>
    </div>
  );
}

function PipelineStepper({ currentStep }: { currentStep: number }) {
  return (
    <div className="flex items-center gap-1 mt-4">
      {Array.from({ length: PIPELINE_STEPS }).map((_, i) => (
        <div
          key={i}
          className={[
            "h-1 flex-1 rounded-full transition-all duration-500",
            i < currentStep
              ? "bg-indigo-500"
              : i === currentStep
                ? "bg-indigo-400 animate-pulse"
                : "bg-zinc-700",
          ].join(" ")}
        />
      ))}
    </div>
  );
}

export default function StageLoadingOverlay() {
  const { agentState, isRunning, error } = useProjectStore();

  const status = agentState?.execution_status ?? "idle";
  const config = STAGE_CONFIG[status];

  const isVisible =
    isRunning ||
    (config.type === "error" && !HIDDEN_STAGES.includes(status)) ||
    (!HIDDEN_STAGES.includes(status) && config.type !== "success");

  if (!isVisible) return null;

  const accentColor =
    config.type === "error"
      ? "text-red-400"
      : config.type === "waiting"
        ? "text-amber-300"
        : "text-indigo-300";

  const borderColor =
    config.type === "error"
      ? "border-red-500/20"
      : config.type === "waiting"
        ? "border-amber-500/20"
        : "border-indigo-500/20";

  return (
    <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10">
      <div
        className={[
          "flex flex-col items-center gap-3 px-8 py-6 rounded-2xl",
          "bg-zinc-950/80 backdrop-blur-md border",
          borderColor,
          "shadow-2xl shadow-black/60 max-w-xs w-full mx-4",
        ].join(" ")}
      >
        {/* Icon */}
        {config.type === "progress" && <Spinner />}
        {config.type === "waiting" && <WaitingPulse />}
        {config.type === "error" && <ErrorIcon />}

        {/* Stage label */}
        <div className="text-center">
          <p className={`text-sm font-semibold tracking-wide uppercase ${accentColor}`}>
            {config.label}
          </p>
          <p className="text-xs text-zinc-400 mt-1 leading-snug">
            {config.description}
          </p>
        </div>

        {/* Pipeline progress bar (only for in-pipeline steps) */}
        {config.step !== null && (
          <PipelineStepper currentStep={config.step} />
        )}

        {/* Error message from store */}
        {error && config.type === "error" && (
          <p className="text-[11px] text-red-400/80 text-center bg-red-950/40 rounded-lg px-3 py-2 w-full leading-snug">
            {error}
          </p>
        )}

        {/* Stage key badge */}
        <p className="text-[10px] text-zinc-600 font-mono">{status}</p>
      </div>
    </div>
  );
}
