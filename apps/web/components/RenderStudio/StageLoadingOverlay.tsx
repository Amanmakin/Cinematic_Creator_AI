"use client";

import { useProjectStore } from "@/state/projectStore";
import type { ExecutionStage } from "@/lib/types/agentState";

interface StageConfig {
  label: string;
  description: string;
  type: "progress" | "waiting" | "success" | "error";
  step: number | null;
  emoji: string;
}

const PIPELINE_STEPS = 14;

const STAGE_CONFIG: Record<ExecutionStage, StageConfig> = {
  idle: {
    label: "Ready",
    description: "Waiting for your prompt",
    type: "success",
    step: null,
    emoji: "🎬",
  },
  intent_validated: {
    label: "Analyzing Intent",
    description: "Parsing your creative vision into cinematic language",
    type: "progress",
    step: 0,
    emoji: "🧠",
  },
  awaiting_human_approval: {
    label: "Awaiting Your Review",
    description: "The scene draft is ready — your eye makes the call",
    type: "waiting",
    step: 1,
    emoji: "👁️",
  },
  speculative_batching: {
    label: "Exploring Variants",
    description: "Running parallel interpretations of your vision",
    type: "progress",
    step: 2,
    emoji: "✨",
  },
  semantic_lock_applied: {
    label: "Locking Creative Elements",
    description: "Pinning your approved choices before generation begins",
    type: "progress",
    step: 3,
    emoji: "🔒",
  },
  scene_graph_generated: {
    label: "Scene Composed",
    description: "3D scene structure has been assembled from intent",
    type: "progress",
    step: 4,
    emoji: "🎥",
  },
  previsualization_generated: {
    label: "Previsualization Ready",
    description: "Wireframe animatic is ready for your review",
    type: "waiting",
    step: 5,
    emoji: "🖼️",
  },
  previsualization_approved: {
    label: "Previsualization Accepted",
    description: "Moving forward with approved camera and lighting",
    type: "progress",
    step: 6,
    emoji: "✅",
  },
  previsualization_feedback: {
    label: "Refining Previsualization",
    description: "Applying your notes to the animatic draft",
    type: "progress",
    step: 6,
    emoji: "✏️",
  },
  model_generated: {
    label: "3D Models Ready",
    description: "Model renders are ready — approve to continue",
    type: "waiting",
    step: 7,
    emoji: "🗿",
  },
  model_approved: {
    label: "Models Accepted",
    description: "Proceeding with approved 3D assets",
    type: "progress",
    step: 8,
    emoji: "✅",
  },
  model_feedback: {
    label: "Refining 3D Models",
    description: "Applying your notes to model generation",
    type: "progress",
    step: 8,
    emoji: "🔧",
  },
  creative_dispatching: {
    label: "Dispatching Creative Work",
    description: "Routing assets to local and cloud generators",
    type: "progress",
    step: 9,
    emoji: "🚀",
  },
  visual_generating: {
    label: "Synthesizing Visuals",
    description: "Generating images and layer assets",
    type: "progress",
    step: 10,
    emoji: "🎨",
  },
  dsl_compiled: {
    label: "Compiling Scene DSL",
    description: "Translating scene description into Blender instructions",
    type: "progress",
    step: 11,
    emoji: "⚙️",
  },
  gltf_assembled: {
    label: "Assembling 3D Scene",
    description: "Merging layers and geometry into glTF",
    type: "progress",
    step: 12,
    emoji: "🧩",
  },
  render_progress: {
    label: "Rendering",
    description: "Blender is processing frames headlessly",
    type: "progress",
    step: 13,
    emoji: "🎞️",
  },
  render_completed: {
    label: "Render Complete",
    description: "All frames rendered — compositing final output",
    type: "success",
    step: null,
    emoji: "🎉",
  },
  completed: {
    label: "Complete",
    description: "Your cinematic scene is ready",
    type: "success",
    step: null,
    emoji: "🏆",
  },
  budget_exceeded: {
    label: "Budget Exceeded",
    description: "Generation cost limit reached — adjust settings and retry",
    type: "error",
    step: null,
    emoji: "💸",
  },
  physical_validation_failed: {
    label: "Physics Violation",
    description: "Scene geometry has constraint violations",
    type: "error",
    step: null,
    emoji: "⚠️",
  },
  dsl_validation_failed: {
    label: "DSL Error",
    description: "Scene description could not be compiled",
    type: "error",
    step: null,
    emoji: "🚫",
  },
  render_timed_out: {
    label: "Render Timed Out",
    description: "The render process exceeded the allowed duration",
    type: "error",
    step: null,
    emoji: "⏱️",
  },
  failed: {
    label: "Failed",
    description: "An unexpected error occurred",
    type: "error",
    step: null,
    emoji: "💥",
  },
};

const HIDDEN_STAGES: ExecutionStage[] = ["idle", "completed", "render_completed"];

// ── Cinematic corner brackets ────────────────────────────────────────────────

function ViewfinderCorners({ color }: { color: string }) {
  const cls = `absolute w-4 h-4 ${color}`;
  const line = "border-current";
  return (
    <>
      <span className={`${cls} top-0 left-0 border-t-2 border-l-2 ${line}`} />
      <span className={`${cls} top-0 right-0 border-t-2 border-r-2 ${line}`} />
      <span className={`${cls} bottom-0 left-0 border-b-2 border-l-2 ${line}`} />
      <span className={`${cls} bottom-0 right-0 border-b-2 border-r-2 ${line}`} />
    </>
  );
}

// ── Animated icons ───────────────────────────────────────────────────────────

function CinematicSpinner({ color }: { color: string }) {
  return (
    <div className="relative flex items-center justify-center w-16 h-16">
      {/* Outer orbit */}
      <div className={`absolute inset-0 rounded-full border-2 border-transparent border-t-current ${color} animate-spin`} />
      {/* Inner counter-orbit */}
      <div
        className={`absolute inset-2 rounded-full border border-transparent border-b-current ${color} opacity-60 animate-spin [animation-duration:1.8s] [animation-direction:reverse]`}
      />
      {/* Dot pulse */}
      <div className={`w-3 h-3 rounded-full bg-current ${color} animate-pulse`} />
    </div>
  );
}

function WaitingPulse({ color }: { color: string }) {
  return (
    <div className="relative flex items-center justify-center w-16 h-16">
      <div className={`absolute inset-0 rounded-full bg-current ${color} opacity-10 animate-ping [animation-duration:2s]`} />
      <div className={`absolute inset-3 rounded-full bg-current ${color} opacity-20 animate-ping [animation-duration:2s] [animation-delay:0.7s]`} />
      <div className={`w-6 h-6 rounded-full bg-current ${color} animate-pulse`} />
    </div>
  );
}

function ErrorIcon() {
  return (
    <div className="relative flex items-center justify-center w-16 h-16">
      <div className="absolute inset-0 rounded-full bg-red-500/10 animate-pulse" />
      <svg className="w-9 h-9 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 4h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      </svg>
    </div>
  );
}

// ── Film-strip stepper ───────────────────────────────────────────────────────

function FilmStepper({ currentStep }: { currentStep: number }) {
  return (
    <div className="w-full flex flex-col gap-1">
      {/* Track */}
      <div className="flex items-center gap-px">
        {/* Sprocket hole left */}
        <div className="flex flex-col gap-1 pr-1">
          {[0, 1].map((i) => (
            <div key={i} className="w-1.5 h-1.5 rounded-full bg-zinc-700" />
          ))}
        </div>

        {/* Frames */}
        {Array.from({ length: PIPELINE_STEPS }).map((_, i) => (
          <div
            key={i}
            className={[
              "h-2 flex-1 rounded-sm transition-all duration-500",
              i < currentStep
                ? "bg-indigo-500"
                : i === currentStep
                  ? "bg-indigo-400 animate-pulse"
                  : "bg-zinc-800",
            ].join(" ")}
          />
        ))}

        {/* Sprocket hole right */}
        <div className="flex flex-col gap-1 pl-1">
          {[0, 1].map((i) => (
            <div key={i} className="w-1.5 h-1.5 rounded-full bg-zinc-700" />
          ))}
        </div>
      </div>

      {/* Step counter */}
      <p className="text-[10px] text-zinc-600 text-center font-mono">
        FRAME {currentStep + 1} / {PIPELINE_STEPS}
      </p>
    </div>
  );
}

// ── Main overlay ─────────────────────────────────────────────────────────────

export default function StageLoadingOverlay() {
  const { agentState, isRunning, error } = useProjectStore();

  const status = agentState?.execution_status ?? "idle";
  const config = STAGE_CONFIG[status] ?? STAGE_CONFIG.idle;

  const isVisible =
    isRunning ||
    (config.type === "error" && !HIDDEN_STAGES.includes(status)) ||
    (config.type === "waiting" && !HIDDEN_STAGES.includes(status)) ||
    (config.type === "progress" && !HIDDEN_STAGES.includes(status));

  if (!isVisible) return null;

  // Color tokens per phase type
  const accentText =
    config.type === "error"
      ? "text-red-400"
      : config.type === "waiting"
        ? "text-amber-300"
        : "text-indigo-300";

  const cornerColor =
    config.type === "error"
      ? "text-red-500/50"
      : config.type === "waiting"
        ? "text-amber-500/50"
        : "text-indigo-500/50";

  const borderColor =
    config.type === "error"
      ? "border-red-500/25"
      : config.type === "waiting"
        ? "border-amber-500/25"
        : "border-indigo-500/25";

  const glowColor =
    config.type === "error"
      ? "shadow-red-950/60"
      : config.type === "waiting"
        ? "shadow-amber-950/60"
        : "shadow-indigo-950/60";

  const iconColor =
    config.type === "error"
      ? "text-red-400"
      : config.type === "waiting"
        ? "text-amber-400"
        : "text-indigo-400";

  return (
    <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10">
      {/* Subtle radial vignette behind the card */}
      <div
        className="absolute inset-0 opacity-60"
        style={{
          background:
            "radial-gradient(ellipse at center, transparent 30%, rgba(0,0,0,0.7) 100%)",
        }}
      />

      {/* Card */}
      <div
        className={[
          "relative flex flex-col items-center gap-4 px-8 py-7 rounded-xl",
          "bg-zinc-950/85 backdrop-blur-lg border",
          borderColor,
          `shadow-2xl ${glowColor}`,
          "max-w-xs w-full mx-4",
        ].join(" ")}
      >
        {/* Viewfinder corners */}
        <ViewfinderCorners color={cornerColor} />

        {/* Emoji phase icon */}
        <div className="text-2xl select-none leading-none">{config.emoji}</div>

        {/* Animated icon */}
        {config.type === "progress" && <CinematicSpinner color={iconColor} />}
        {config.type === "waiting" && <WaitingPulse color={iconColor} />}
        {config.type === "error" && <ErrorIcon />}

        {/* Phase label + description */}
        <div className="text-center space-y-1">
          <p className={`text-sm font-bold tracking-widest uppercase ${accentText}`}>
            {config.label}
          </p>
          <p className="text-xs text-zinc-400 leading-snug">{config.description}</p>
        </div>

        {/* Film-strip progress */}
        {config.step !== null && <FilmStepper currentStep={config.step} />}

        {/* Error detail */}
        {error && config.type === "error" && (
          <p className="text-[11px] text-red-400/80 text-center bg-red-950/40 rounded-lg px-3 py-2 w-full leading-snug">
            {error}
          </p>
        )}

        {/* Monospace status key */}
        <p className="text-[10px] text-zinc-700 font-mono tracking-wide">{status}</p>
      </div>
    </div>
  );
}
