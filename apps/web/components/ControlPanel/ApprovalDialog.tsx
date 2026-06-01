"use client";

import { useState, useEffect } from "react";
import { useProjectStore } from "@/state/projectStore";

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

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
function toAssetUrl(path: string) {
  return path.startsWith("http") ? path : `${API_BASE}${path}`;
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
                onClick={() => setLightboxSrc(toAssetUrl(src))}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={toAssetUrl(src)} alt={`Render ${i}`} className="w-full h-16 object-cover" />
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
  const isWireframe = agentState.execution_status === "previsualization_generated";
  const isModel = agentState.execution_status === "model_generated";

  if (!isHumanApproval && !isWireframe && !isModel) return null;

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

  // Centered modal for human approval
  const title = isHumanApproval ? "Ambiguous Prompt — Human Approval Required" : "";

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

      </div>
    </div>
  );
}
