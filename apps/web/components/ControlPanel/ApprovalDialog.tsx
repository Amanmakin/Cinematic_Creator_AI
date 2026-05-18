"use client";

import { useState } from "react";
import { useProjectStore } from "@/state/projectStore";
import type { BlenderDsl, WireframeFrame } from "@/lib/types/agentState";

// ─── Wireframe Approval Panel ──────────────────────────────────────────────

function WireframePanel() {
  const { agentState, approve, isRunning } = useProjectStore();
  const [notes, setNotes] = useState("");

  if (!agentState) return null;

  const previs = agentState.previsualization;
  const isWireframeMode = agentState.generation_mode === "wireframe";

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-slate-400">
        Wireframe previsualization complete — {previs?.frames.length ?? 0} frame
        {previs?.frames.length !== 1 ? "s" : ""} rendered.
        Mood: <span className="text-slate-200">{previs?.mood}</span>. Palette:{" "}
        <span className="text-slate-200">{previs?.palette_hint}</span>.
      </p>

      {/* Thumbnail strip */}
      {previs && previs.frames.length > 0 && (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {previs.frames.map((frame: WireframeFrame) => (
            <div
              key={frame.frame_index}
              className="flex-shrink-0 w-40 rounded-md overflow-hidden border border-border bg-surface"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={frame.viewport_thumbnail_path}
                alt={`Frame ${frame.frame_index}`}
                className="w-full h-24 object-cover"
              />
              <div className="px-2 py-1 text-[10px] text-slate-400 leading-tight">
                <div>
                  {frame.time_start_s.toFixed(1)}s – {frame.time_end_s.toFixed(1)}s
                </div>
                <div>focal {frame.camera.focal_length_mm}mm</div>
                {frame.notes && (
                  <div className="truncate text-slate-500">{frame.notes}</div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Revision notes */}
      <textarea
        className="bg-surface border border-border rounded-md p-3 text-sm text-slate-200 resize-none h-16 focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-slate-600"
        placeholder="Revision notes (required for Modify)…"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />

      <div className="flex gap-2">
        {/* Approve — hidden when mode is wireframe-only */}
        {!isWireframeMode && (
          <button
            className="flex-1 bg-accent hover:bg-indigo-500 disabled:opacity-40 text-white text-sm rounded-md py-2 transition-colors"
            disabled={isRunning}
            onClick={() => approve("previsualization_approve" as never)}
          >
            Approve
          </button>
        )}

        {/* Proceed to Model Generation — shown only when mode is wireframe */}
        {isWireframeMode && (
          <button
            className="flex-1 bg-accent hover:bg-indigo-500 disabled:opacity-40 text-white text-sm rounded-md py-2 transition-colors"
            disabled={isRunning}
            onClick={() => approve("previsualization_proceed" as never)}
          >
            Proceed to Model Generation
          </button>
        )}

        <button
          className="flex-1 bg-surface border border-border hover:border-accent disabled:opacity-40 text-slate-200 text-sm rounded-md py-2 transition-colors"
          disabled={isRunning || !notes.trim()}
          onClick={() => approve("previsualization_modify" as never, { notes: notes.trim() })}
        >
          Modify
        </button>

        <button
          className="flex-1 bg-red-900/40 border border-red-700/50 hover:border-red-500 disabled:opacity-40 text-red-300 text-sm rounded-md py-2 transition-colors"
          disabled={isRunning}
          onClick={() => approve("previsualization_reject" as never)}
        >
          Reject
        </button>
      </div>
    </div>
  );
}

// ─── Model Approval Panel ──────────────────────────────────────────────────

function ModelPanel() {
  const { agentState, approve, isRunning } = useProjectStore();
  const [notes, setNotes] = useState("");
  const [showWireframes, setShowWireframes] = useState(false);

  if (!agentState) return null;

  const previs = agentState.previsualization;
  const modelRenders = agentState.model_renders ?? [];
  const isModelMode = agentState.generation_mode === "model";

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-slate-400">
        Model renders complete — {modelRenders.length} render
        {modelRenders.length !== 1 ? "s" : ""} generated.
      </p>

      {/* Model renders */}
      {modelRenders.length > 0 && (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {modelRenders.map((src: string, i: number) => (
            <div
              key={i}
              className="flex-shrink-0 w-40 rounded-md overflow-hidden border border-border bg-surface"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={src}
                alt={`Model render ${i}`}
                className="w-full h-24 object-cover"
              />
            </div>
          ))}
        </div>
      )}

      {/* Collapsible wireframe reference */}
      {previs && previs.frames.length > 0 && (
        <div>
          <button
            className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
            onClick={() => setShowWireframes((v) => !v)}
          >
            {showWireframes ? "▲ Hide wireframe reference" : "▼ Show wireframe reference"}
          </button>
          {showWireframes && (
            <div className="flex gap-2 overflow-x-auto pb-1 mt-2">
              {previs.frames.map((frame: WireframeFrame) => (
                <div
                  key={frame.frame_index}
                  className="flex-shrink-0 w-32 rounded-md overflow-hidden border border-border/50 bg-surface opacity-70"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={frame.viewport_thumbnail_path}
                    alt={`Frame ${frame.frame_index}`}
                    className="w-full h-20 object-cover"
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Revision notes */}
      <textarea
        className="bg-surface border border-border rounded-md p-3 text-sm text-slate-200 resize-none h-16 focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-slate-600"
        placeholder="Revision notes (required for Modify)…"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />

      <div className="flex gap-2">
        {/* Approve — hidden when mode is model-only */}
        {!isModelMode && (
          <button
            className="flex-1 bg-accent hover:bg-indigo-500 disabled:opacity-40 text-white text-sm rounded-md py-2 transition-colors"
            disabled={isRunning}
            onClick={() => approve("model_approve" as never)}
          >
            Approve
          </button>
        )}

        {/* Proceed to Video Generation — shown only when mode is model */}
        {isModelMode && (
          <button
            className="flex-1 bg-accent hover:bg-indigo-500 disabled:opacity-40 text-white text-sm rounded-md py-2 transition-colors"
            disabled={isRunning}
            onClick={() => approve("model_proceed" as never)}
          >
            Proceed to Video Generation
          </button>
        )}

        <button
          className="flex-1 bg-surface border border-border hover:border-accent disabled:opacity-40 text-slate-200 text-sm rounded-md py-2 transition-colors"
          disabled={isRunning || !notes.trim()}
          onClick={() => approve("model_modify" as never, { notes: notes.trim() })}
        >
          Modify
        </button>

        <button
          className="flex-1 bg-red-900/40 border border-red-700/50 hover:border-red-500 disabled:opacity-40 text-red-300 text-sm rounded-md py-2 transition-colors"
          disabled={isRunning}
          onClick={() => approve("model_reject" as never)}
        >
          Reject
        </button>
      </div>
    </div>
  );
}

// ─── Root dialog ──────────────────────────────────────────────────────────

export default function ApprovalDialog() {
  const { agentState, approve, isRunning } = useProjectStore();
  const [modifiedPrompt, setModifiedPrompt] = useState("");

  if (!agentState) return null;

  const isHumanApproval = agentState.execution_status === "awaiting_human_approval";
  const isSpeculative = agentState.execution_status === "speculative_batching";
  const isWireframe = agentState.execution_status === "previsualization_generated";
  const isModel = agentState.execution_status === "model_generated";

  if (!isHumanApproval && !isSpeculative && !isWireframe && !isModel) return null;

  let title = "";
  if (isHumanApproval) title = "Ambiguous Prompt — Human Approval Required";
  else if (isSpeculative) title = "Pick a Speculative Variant";
  else if (isWireframe) title = "Wireframe Previsualization — Review & Approve";
  else if (isModel) title = "Model Renders — Review & Approve";

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-panel border border-border rounded-xl w-full max-w-2xl p-6 flex flex-col gap-4 shadow-2xl">
        <h2 className="text-base font-semibold text-white">{title}</h2>

        {isHumanApproval && (
          <>
            <p className="text-sm text-slate-400">
              The intent validator flagged high ambiguity (score:{" "}
              {agentState.ambiguity_score.toFixed(2)}). Accept the current
              interpretation or supply a clarified prompt.
            </p>
            <textarea
              className="bg-surface border border-border rounded-md p-3 text-sm text-slate-200 resize-none h-20 focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-slate-600"
              placeholder="Clarified prompt (leave empty to accept as-is)…"
              value={modifiedPrompt}
              onChange={(e) => setModifiedPrompt(e.target.value)}
            />
            <div className="flex gap-2">
              <button
                className="flex-1 bg-accent hover:bg-indigo-500 disabled:opacity-40 text-white text-sm rounded-md py-2 transition-colors"
                disabled={isRunning}
                onClick={() =>
                  modifiedPrompt.trim()
                    ? approve("modify", { modified_prompt: modifiedPrompt.trim() })
                    : approve("accept")
                }
              >
                {modifiedPrompt.trim() ? "Submit Modified Prompt" : "Accept"}
              </button>
            </div>
          </>
        )}

        {isSpeculative && (
          <>
            <p className="text-sm text-slate-400">
              The engine generated {agentState.speculative_variants.length} variants.
              Pick one to continue.
            </p>
            <div className="flex flex-col gap-2 max-h-64 overflow-y-auto">
              {agentState.speculative_variants.map((variant: BlenderDsl, i: number) => (
                <button
                  key={i}
                  className="bg-surface border border-border hover:border-accent rounded-lg p-3 text-left text-xs text-slate-300 hover:text-white transition-colors"
                  disabled={isRunning}
                  onClick={() => approve("select_variant", { variant_index: i })}
                >
                  <span className="font-semibold text-accent">
                    Variant {String.fromCharCode(65 + i)}
                  </span>
                  {" — "}fps: {variant.scene?.fps ?? "?"}
                  {", "}focal: {variant.scene?.camera?.focal_mm ?? "?"}mm
                </button>
              ))}
            </div>
          </>
        )}

        {isWireframe && <WireframePanel />}

        {isModel && <ModelPanel />}
      </div>
    </div>
  );
}
