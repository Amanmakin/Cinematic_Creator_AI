"use client";

import { useState, useEffect } from "react";
import { useProjectStore } from "@/state/projectStore";
import type { BlenderDsl } from "@/lib/types/agentState";

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
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  if (!agentState) return null;

  return (
    <>
      <p className="text-sm text-zinc-300">
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
              className={`bg-zinc-800 border rounded-lg p-3 text-left transition-colors group ${
                selectedIndex === i
                  ? "border-indigo-400 bg-indigo-500/10"
                  : "border-zinc-600 hover:border-indigo-400"
              }`}
              disabled={isRunning}
              onClick={() => {
                setSelectedIndex(i);
                approve("select_variant", { variant_index: i });
              }}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-indigo-400 flex items-center gap-2">
                  Variant {String.fromCharCode(65 + i)}
                  {isRunning && selectedIndex === i && (
                    <svg className="animate-spin h-3 w-3 text-indigo-400" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                    </svg>
                  )}
                </span>
                <span className="text-[10px] text-zinc-400 group-hover:text-zinc-200 transition-colors">
                  {dur.toFixed(1)}s · {fps} fps
                </span>
              </div>

              <div className="flex gap-4 mb-2">
                <div className="flex flex-col">
                  <span className="text-[10px] text-zinc-400 uppercase tracking-wider">Lens</span>
                  <span className="text-xs text-zinc-100">{focal}mm</span>
                  <span className="text-[10px] text-zinc-400">{lensLabel}</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[10px] text-zinc-400 uppercase tracking-wider">Lighting</span>
                  <span className="text-xs text-zinc-100">{lightMood}</span>
                  <span className="text-[10px] text-zinc-400">{lights.length} light{lights.length !== 1 ? "s" : ""}</span>
                </div>
                {subjects.length > 0 && (
                  <div className="flex flex-col flex-1 min-w-0">
                    <span className="text-[10px] text-zinc-400 uppercase tracking-wider">Subject</span>
                    <span className="text-xs text-zinc-100 truncate">
                      {subjects[0]?.description ?? "—"}
                    </span>
                    {subjects.length > 1 && (
                      <span className="text-[10px] text-zinc-400">+{subjects.length - 1} more</span>
                    )}
                  </div>
                )}
              </div>

              <div className="w-full h-1 bg-zinc-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-indigo-400/60 rounded-full"
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
              ? "bg-zinc-800 border-indigo-400"
              : "bg-zinc-800 border-zinc-600 hover:border-indigo-400 cursor-pointer"
          }`}
          onClick={() => { if (!showCustom) setShowCustom(true); }}
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-semibold text-indigo-400">Custom</span>
            <span className="text-[10px] text-zinc-400">Describe your own</span>
          </div>

          {!showCustom ? (
            <p className="text-xs text-zinc-400">
              Click to describe exactly what you want — lens, lighting, subject, mood, etc.
            </p>
          ) : (
            <div className="flex flex-col gap-2" onClick={(e) => e.stopPropagation()}>
              <textarea
                autoFocus
                className="bg-zinc-900 border border-zinc-600 rounded-md p-2 text-sm text-zinc-100 resize-none h-24 focus:outline-none focus:ring-2 focus:ring-indigo-500/60 focus:border-indigo-500 placeholder:text-zinc-500 w-full"
                placeholder="e.g. A matte black water bottle, 85mm portrait lens, warm rim lighting from the left, dark studio background…"
                value={customText}
                onChange={(e) => setCustomText(e.target.value)}
              />
              <div className="flex gap-2">
                <button
                  className="flex-1 bg-indigo-500 hover:bg-indigo-400 disabled:opacity-40 text-white text-sm rounded-md py-2 transition-colors"
                  disabled={isRunning || !customText.trim()}
                  onClick={() => approve("modify", { modified_prompt: customText.trim() })}
                >
                  Generate Custom Variant
                </button>
                <button
                  className="px-3 bg-zinc-800 border border-zinc-600 hover:border-zinc-400 text-zinc-300 text-sm rounded-md py-2 transition-colors"
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
  const [feedbackOpen, setFeedbackOpen] = useState(false);

  if (!agentState) return null;

  const previs = agentState.previsualization;
  const frameCount = previs?.frames.length ?? 0;

  return (
    <div className="flex flex-col gap-2">
      {/* Meta row */}
      <div className="flex items-center gap-4 text-xs text-zinc-400">
        <span className="text-zinc-100 font-medium">Wireframe Previsualization</span>
        <span>{frameCount} frame{frameCount !== 1 ? "s" : ""}</span>
        {previs?.mood && <span>Mood: <span className="text-zinc-100">{previs.mood}</span></span>}
        {previs?.palette_hint && <span>Palette: <span className="text-zinc-100">{previs.palette_hint}</span></span>}
      </div>

      {/* Feedback textarea — only shown when open */}
      {feedbackOpen && (
        <textarea
          autoFocus
          className="bg-zinc-900 border border-zinc-600 rounded-md p-2 text-sm text-zinc-100 resize-none h-16 focus:outline-none focus:ring-2 focus:ring-indigo-500/60 focus:border-indigo-500 placeholder:text-zinc-500 w-full"
          placeholder="Describe what to change…"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      )}

      {/* Action row */}
      <div className="flex gap-2">
        {!feedbackOpen ? (
          <button
            className="px-4 bg-zinc-800 border border-zinc-600 hover:border-zinc-400 disabled:opacity-40 text-zinc-200 text-sm rounded-md py-1.5 transition-colors"
            disabled={isRunning}
            onClick={() => setFeedbackOpen(true)}
          >
            Feedback
          </button>
        ) : (
          <>
            <button
              className="px-4 bg-zinc-800 border border-zinc-600 hover:border-zinc-400 text-zinc-300 text-sm rounded-md py-1.5 transition-colors"
              onClick={() => { setFeedbackOpen(false); setNotes(""); }}
            >
              Cancel
            </button>
            <button
              className="px-4 bg-indigo-500 hover:bg-indigo-400 disabled:opacity-40 text-white text-sm rounded-md py-1.5 transition-colors"
              disabled={isRunning || !notes.trim()}
              onClick={() => {
                approve("previsualization_modify", { notes: notes.trim() });
                setFeedbackOpen(false);
                setNotes("");
              }}
            >
              Submit
            </button>
          </>
        )}
        <button
          className="px-5 bg-indigo-500 hover:bg-indigo-400 disabled:opacity-40 text-white text-sm rounded-md py-1.5 transition-colors ml-auto"
          disabled={isRunning}
          onClick={() => approve("previsualization_approve")}
        >
          Approve
        </button>
      </div>
    </div>
  );
}

// ─── Model Approval Panel ──────────────────────────────────────────────────

function ModelPanel() {
  const { agentState, approve, isRunning } = useProjectStore();
  const [notes, setNotes] = useState("");
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);

  if (!agentState) return null;

  const modelRenders = agentState.model_renders ?? [];

  return (
    <>
      {lightboxSrc && <Lightbox src={lightboxSrc} onClose={() => setLightboxSrc(null)} />}
      <div className="flex flex-col gap-2">
        {/* Render thumbnails strip */}
        {modelRenders.length > 0 && (
          <div className="flex gap-2 overflow-x-auto pb-1">
            {modelRenders.map((src: string, i: number) => (
              <div
                key={i}
                className="flex-shrink-0 w-28 rounded-md overflow-hidden border border-zinc-600 bg-zinc-800 cursor-zoom-in"
                onClick={() => setLightboxSrc(src)}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={src} alt={`Render ${i}`} className="w-full h-16 object-cover" />
              </div>
            ))}
          </div>
        )}

        {/* Meta row */}
        <div className="flex items-center gap-4 text-xs text-zinc-400">
          <span className="text-zinc-100 font-medium">Model Renders</span>
          <span>{modelRenders.length} render{modelRenders.length !== 1 ? "s" : ""}</span>
        </div>

        {/* Feedback textarea */}
        {feedbackOpen && (
          <textarea
            autoFocus
            className="bg-zinc-900 border border-zinc-600 rounded-md p-2 text-sm text-zinc-100 resize-none h-16 focus:outline-none focus:ring-2 focus:ring-indigo-500/60 focus:border-indigo-500 placeholder:text-zinc-500 w-full"
            placeholder="Describe what to change…"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        )}

        <div className="flex gap-2">
          {!feedbackOpen ? (
            <button
              className="px-4 bg-surface border border-border hover:border-slate-400 disabled:opacity-40 text-slate-300 text-sm rounded-md py-1.5 transition-colors"
              disabled={isRunning}
              onClick={() => setFeedbackOpen(true)}
            >
              Feedback
            </button>
          ) : (
            <>
              <button
                className="px-4 bg-surface border border-border hover:border-slate-400 text-slate-400 text-sm rounded-md py-1.5 transition-colors"
                onClick={() => { setFeedbackOpen(false); setNotes(""); }}
              >
                Cancel
              </button>
              <button
                className="px-4 bg-accent hover:bg-indigo-500 disabled:opacity-40 text-white text-sm rounded-md py-1.5 transition-colors"
                disabled={isRunning || !notes.trim()}
                onClick={() => {
                  approve("model_modify", { notes: notes.trim() });
                  setFeedbackOpen(false);
                  setNotes("");
                }}
              >
                Submit
              </button>
            </>
          )}
          <button
            className="px-5 bg-accent hover:bg-indigo-500 disabled:opacity-40 text-white text-sm rounded-md py-1.5 transition-colors ml-auto"
            disabled={isRunning}
            onClick={() => approve("model_approve")}
          >
            Approve
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

  // Once the user has acted and the pipeline is running, hide approval UI so the
  // loading overlay can take over.
  if (isRunning && (isWireframe || isModel)) return null;

  // Wireframe and model use the slim bottom bar; other states use the centered modal.
  if (isWireframe) {
    return (
      <div className="fixed bottom-0 left-0 right-0 z-50 bg-zinc-900/95 backdrop-blur border-t border-zinc-700 px-6 py-3 shadow-2xl">
        <WireframePanel />
      </div>
    );
  }

  if (isModel) {
    return (
      <div className="fixed bottom-0 left-0 right-0 z-50 bg-panel/95 backdrop-blur border-t border-border px-6 py-3 shadow-2xl">
        <ModelPanel />
      </div>
    );
  }

  // Centered modal for human approval and speculative batching
  let title = "";
  if (isHumanApproval) title = "Ambiguous Prompt — Human Approval Required";
  else if (isSpeculative) title = "Pick a Speculative Variant";

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl w-full max-w-2xl p-6 flex flex-col gap-4 shadow-2xl">
        <h2 className="text-base font-semibold text-white">{title}</h2>

        {isHumanApproval && (
          <>
            <p className="text-sm text-zinc-300">
              The intent validator flagged high ambiguity (score:{" "}
              {agentState.ambiguity_score.toFixed(2)}). Accept the current
              interpretation or supply a clarified prompt.
            </p>
            <textarea
              className="bg-zinc-800 border border-zinc-600 rounded-md p-3 text-sm text-zinc-100 resize-none h-20 focus:outline-none focus:ring-2 focus:ring-indigo-500/60 focus:border-indigo-500 placeholder:text-zinc-500"
              placeholder="Clarified prompt (leave empty to accept as-is)…"
              value={modifiedPrompt}
              onChange={(e) => setModifiedPrompt(e.target.value)}
            />
            <div className="flex gap-2">
              <button
                className="flex-1 bg-indigo-500 hover:bg-indigo-400 disabled:opacity-40 text-white text-sm rounded-md py-2 transition-colors"
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
      </div>
    </div>
  );
}
