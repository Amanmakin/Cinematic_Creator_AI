"use client";

import { useState } from "react";
import { useProjectStore } from "@/state/projectStore";
import type { BlenderDsl } from "@/lib/types/agentState";

export default function ApprovalDialog() {
  const { agentState, approve, isRunning } = useProjectStore();
  const [modifiedPrompt, setModifiedPrompt] = useState("");

  if (!agentState) return null;

  const isHumanApproval = agentState.execution_status === "awaiting_human_approval";
  const isSpeculative = agentState.execution_status === "speculative_batching";

  if (!isHumanApproval && !isSpeculative) return null;

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-panel border border-border rounded-xl w-full max-w-lg p-6 flex flex-col gap-4 shadow-2xl">
        <h2 className="text-base font-semibold text-white">
          {isHumanApproval ? "Ambiguous Prompt — Human Approval Required" : "Pick a Speculative Variant"}
        </h2>

        {isHumanApproval && (
          <>
            <p className="text-sm text-slate-400">
              The intent validator flagged high ambiguity (score: {agentState.ambiguity_score.toFixed(2)}).
              Accept the current interpretation or supply a clarified prompt.
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
              The engine generated {agentState.speculative_variants.length} variants. Pick one to continue.
            </p>
            <div className="flex flex-col gap-2 max-h-64 overflow-y-auto">
              {agentState.speculative_variants.map((variant: BlenderDsl, i: number) => (
                <button
                  key={i}
                  className="bg-surface border border-border hover:border-accent rounded-lg p-3 text-left text-xs text-slate-300 hover:text-white transition-colors"
                  disabled={isRunning}
                  onClick={() => approve("select_variant", { variant_index: i })}
                >
                  <span className="font-semibold text-accent">Variant {String.fromCharCode(65 + i)}</span>
                  {" — "}fps: {variant.scene?.fps ?? "?"}
                  {", "}focal: {variant.scene?.camera?.focal_mm ?? "?"}mm
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
