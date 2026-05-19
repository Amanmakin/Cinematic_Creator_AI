"use client";

import { useState, useEffect } from "react";
import { useProjectStore } from "@/state/projectStore";
import type { BlenderDsl, WireframeFrame } from "@/lib/types/agentState";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function previsUrl(path: string): string {
  return path.startsWith("http") ? path : `${API_BASE}${path}`;
}

function Lightbox({ src, onClose }: { src: string; onClose: () => void }) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 bg-black/90 flex items-center justify-center z-[60]"
      onClick={onClose}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt="Full-screen preview"
        className="max-w-[90vw] max-h-[90vh] object-contain rounded-lg shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      />
      <button
        className="absolute top-4 right-4 text-white/70 hover:text-white text-2xl leading-none"
        onClick={onClose}
      >
        ✕
      </button>
    </div>
  );
}

// ─── Speculative Variant Panel ─────────────────────────────────────────────

function SpeculativePanel() {
  const { agentState, approve, isRunning } = useProjectStore();
  const [customText, setCustomText] = useState("");
  const [showCustom, setShowCustom] = useState(false);

  if (!agentState) return null;

  return (
    <>
      <p className="text-sm text-slate-400">
        The engine generated {agentState.speculative_variants.length} variants.
        Pick one to continue rendering, or describe your own.
      </p>
      <div className="flex flex-col gap-2 max-h-96 overflow-y-auto pr-1">
        {agentState.speculative_variants.map((variant: BlenderDsl, i: number) => {
          const scene = variant.scene;
          const focal = scene?.camera?.focal_mm ?? 50;
          const dur   = scene?.duration_s ?? 0;
          const fps   = scene?.fps ?? 24;
          const lights = scene?.lights ?? [];
          const subjects = scene?.subjects ?? [];
          const keyLight = lights.find((l: { kind: string }) => l.kind === "key");
          const lensLabel =
            focal <= 28  ? "Ultra-wide" :
            focal <= 40  ? "Wide"        :
            focal <= 65  ? "Normal"      :
            focal <= 100 ? "Portrait"    : "Telephoto";
          const moodKelvin = keyLight?.color_kelvin ?? 5600;
          const lightMood =
            moodKelvin < 3500 ? "Warm / golden" :
            moodKelvin < 5000 ? "Neutral"        :
            moodKelvin < 7000 ? "Daylight"       : "Cool / overcast";

          return (
            <button
              key={i}
              className="bg-surface border border-border hover:border-accent rounded-lg p-3 text-left transition-colors group"
              disabled={isRunning}
              onClick={() => approve("select_variant", { variant_index: i })}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-accent">
                  Variant {String.fromCharCode(65 + i)}
                </span>
                <span className="text-[10px] text-slate-500 group-hover:text-slate-300 transition-colors">
                  {dur.toFixed(1)}s · {fps} fps
                </span>
              </div>

              <div className="flex gap-4 mb-2">
                <div className="flex flex-col">
                  <span className="text-[10px] text-slate-500 uppercase tracking-wider">Lens</span>
                  <span className="text-xs text-slate-200">{focal}mm</span>
                  <span className="text-[10px] text-slate-500">{lensLabel}</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[10px] text-slate-500 uppercase tracking-wider">Lighting</span>
                  <span className="text-xs text-slate-200">{lightMood}</span>
                  <span className="text-[10px] text-slate-500">{lights.length} light{lights.length !== 1 ? "s" : ""}</span>
                </div>
                {subjects.length > 0 && (
                  <div className="flex flex-col flex-1 min-w-0">
                    <span className="text-[10px] text-slate-500 uppercase tracking-wider">Subject</span>
                    <span className="text-xs text-slate-200 truncate">
                      {subjects[0]?.description ?? "—"}
                    </span>
                    {subjects.length > 1 && (
                      <span className="text-[10px] text-slate-500">+{subjects.length - 1} more</span>
                    )}
                  </div>
                )}
              </div>

              <div className="w-full h-1 bg-border rounded-full overflow-hidden">
                <div
                  className="h-full bg-accent/60 rounded-full"
                  style={{ width: `${Math.min((dur / 30) * 100, 100)}%` }}
                />
              </div>
            </button>
          );
        })}

        {/* Custom variant card */}
        <div
          className={`border rounded-lg p-3 transition-colors ${
            showCustom
              ? "bg-surface border-accent"
              : "bg-surface border-border hover:border-accent cursor-pointer"
          }`}
          onClick={() => { if (!showCustom) setShowCustom(true); }}
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-semibold text-accent">Custom</span>
            <span className="text-[10px] text-slate-500">Describe your own</span>
          </div>

          {!showCustom ? (
            <p className="text-xs text-slate-500">
              Click to describe exactly what you want — lens, lighting, subject, mood, etc.
            </p>
          ) : (
            <div className="flex flex-col gap-2" onClick={(e) => e.stopPropagation()}>
              <textarea
                autoFocus
                className="bg-black/30 border border-border rounded-md p-2 text-sm text-slate-200 resize-none h-24 focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-slate-600 w-full"
                placeholder="e.g. A matte black water bottle, 85mm portrait lens, warm rim lighting from the left, dark studio background…"
                value={customText}
                onChange={(e) => setCustomText(e.target.value)}
              />
              <div className="flex gap-2">
                <button
                  className="flex-1 bg-accent hover:bg-indigo-500 disabled:opacity-40 text-white text-sm rounded-md py-2 transition-colors"
                  disabled={isRunning || !customText.trim()}
                  onClick={() => approve("modify", { modified_prompt: customText.trim() })}
                >
                  Generate Custom Variant
                </button>
                <button
                  className="px-3 bg-surface border border-border hover:border-slate-400 text-slate-400 text-sm rounded-md py-2 transition-colors"
                  onClick={() => { setShowCustom(false); setCustomText(""); }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

// ─── Wireframe Approval Panel ──────────────────────────────────────────────

function WireframePanel() {
  const { agentState, approve, isRunning } = useProjectStore();
  const [notes, setNotes] = useState("");
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);

  if (!agentState) return null;

  const previs = agentState.previsualization;
  const isWireframeMode = agentState.generation_mode === "wireframe";

  return (
    <>
      {lightboxSrc && <Lightbox src={lightboxSrc} onClose={() => setLightboxSrc(null)} />}
      <div className="flex flex-col gap-4">
        <p className="text-sm text-slate-400">
          Wireframe previsualization complete — {previs?.frames.length ?? 0} frame
          {previs?.frames.length !== 1 ? "s" : ""} rendered.
          Mood: <span className="text-slate-200">{previs?.mood}</span>. Palette:{" "}
          <span className="text-slate-200">{previs?.palette_hint}</span>.
        </p>

        {previs && previs.frames.length > 0 && (
          <div className="flex gap-2 overflow-x-auto pb-1">
            {previs.frames.map((frame: WireframeFrame) => (
              <div
                key={frame.frame_index}
                className="flex-shrink-0 w-40 rounded-md overflow-hidden border border-border bg-surface cursor-zoom-in"
                onClick={() => setLightboxSrc(previsUrl(frame.viewport_thumbnail_path))}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={previsUrl(frame.viewport_thumbnail_path)}
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

        <textarea
          className="bg-surface border border-border rounded-md p-3 text-sm text-slate-200 resize-none h-16 focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-slate-600"
          placeholder="Revision notes (required for Modify)…"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />

        <div className="flex gap-2">
          <button
            className="flex-1 bg-accent hover:bg-indigo-500 disabled:opacity-40 text-white text-sm rounded-md py-2 transition-colors"
            disabled={isRunning}
            onClick={() => approve("previsualization_approve")}
          >
            {isWireframeMode ? "Accept Wireframes" : "Approve"}
          </button>

          {isWireframeMode && (
            <button
              className="flex-1 bg-indigo-700 hover:bg-indigo-600 disabled:opacity-40 text-white text-sm rounded-md py-2 transition-colors"
              disabled={isRunning}
              onClick={() => approve("previsualization_proceed")}
            >
              Make Model
            </button>
          )}

          <button
            className="flex-1 bg-surface border border-border hover:border-accent disabled:opacity-40 text-slate-200 text-sm rounded-md py-2 transition-colors"
            disabled={isRunning || !notes.trim()}
            onClick={() => approve("previsualization_modify", { notes: notes.trim() })}
          >
            Modify
          </button>

          <button
            className="flex-1 bg-red-900/40 border border-red-700/50 hover:border-red-500 disabled:opacity-40 text-red-300 text-sm rounded-md py-2 transition-colors"
            disabled={isRunning}
            onClick={() => approve("previsualization_reject")}
          >
            Reject
          </button>
        </div>
      </div>
    </>
  );
}

// ─── Model Approval Panel ──────────────────────────────────────────────────

function ModelPanel() {
  const { agentState, approve, isRunning } = useProjectStore();
  const [notes, setNotes] = useState("");
  const [showWireframes, setShowWireframes] = useState(false);
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);

  if (!agentState) return null;

  const previs = agentState.previsualization;
  const modelRenders = agentState.model_renders ?? [];
  const isModelMode = agentState.generation_mode === "model";

  return (
    <>
      {lightboxSrc && <Lightbox src={lightboxSrc} onClose={() => setLightboxSrc(null)} />}
      <div className="flex flex-col gap-4">
        <p className="text-sm text-slate-400">
          Model renders complete — {modelRenders.length} render
          {modelRenders.length !== 1 ? "s" : ""} generated.
        </p>

        {modelRenders.length > 0 && (
          <div className="flex gap-2 overflow-x-auto pb-1">
            {modelRenders.map((src: string, i: number) => (
              <div
                key={i}
                className="flex-shrink-0 w-40 rounded-md overflow-hidden border border-border bg-surface cursor-zoom-in"
                onClick={() => setLightboxSrc(src)}
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
                    className="flex-shrink-0 w-32 rounded-md overflow-hidden border border-border/50 bg-surface opacity-70 cursor-zoom-in"
                    onClick={() => setLightboxSrc(previsUrl(frame.viewport_thumbnail_path))}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={previsUrl(frame.viewport_thumbnail_path)}
                      alt={`Frame ${frame.frame_index}`}
                      className="w-full h-20 object-cover"
                    />
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <textarea
          className="bg-surface border border-border rounded-md p-3 text-sm text-slate-200 resize-none h-16 focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-slate-600"
          placeholder="Revision notes (required for Modify)…"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />

        <div className="flex gap-2">
          <button
            className="flex-1 bg-accent hover:bg-indigo-500 disabled:opacity-40 text-white text-sm rounded-md py-2 transition-colors"
            disabled={isRunning}
            onClick={() => approve("model_approve")}
          >
            {isModelMode ? "Accept Models" : "Approve"}
          </button>

          {isModelMode && (
            <button
              className="flex-1 bg-indigo-700 hover:bg-indigo-600 disabled:opacity-40 text-white text-sm rounded-md py-2 transition-colors"
              disabled={isRunning}
              onClick={() => approve("model_proceed")}
            >
              Make Video
            </button>
          )}

          <button
            className="flex-1 bg-surface border border-border hover:border-accent disabled:opacity-40 text-slate-200 text-sm rounded-md py-2 transition-colors"
            disabled={isRunning || !notes.trim()}
            onClick={() => approve("model_modify", { notes: notes.trim() })}
          >
            Modify
          </button>

          <button
            className="flex-1 bg-red-900/40 border border-red-700/50 hover:border-red-500 disabled:opacity-40 text-red-300 text-sm rounded-md py-2 transition-colors"
            disabled={isRunning}
            onClick={() => approve("model_reject")}
          >
            Reject
          </button>
        </div>
      </div>
    </>
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

        {isSpeculative && <SpeculativePanel />}

        {isWireframe && <WireframePanel />}

        {isModel && <ModelPanel />}
      </div>
    </div>
  );
}
