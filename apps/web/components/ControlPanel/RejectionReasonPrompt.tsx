"use client";

import { useState } from "react";
import { rejectIntent } from "@/lib/api";
import { useProjectStore } from "@/state/projectStore";

interface Props {
  onClose: () => void;
}

export default function RejectionReasonPrompt({ onClose }: Props) {
  const { projectId, agentState } = useProjectStore();
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isVisible =
    agentState?.execution_status === "awaiting_human_approval" ||
    agentState?.execution_status === "intent_validated";

  if (!isVisible || !projectId) return null;

  async function handleReject() {
    if (!reason.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await rejectIntent(projectId!, reason.trim());
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Rejection failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-panel border border-border rounded-xl w-full max-w-md p-6 flex flex-col gap-4 shadow-2xl">
        <h2 className="text-base font-semibold text-white">Reject This Direction</h2>
        <p className="text-sm text-slate-400">
          Describe what you want to avoid. This is saved to memory so the model won't
          suggest it again.
        </p>

        <textarea
          className="bg-surface border border-border rounded-md p-3 text-sm text-slate-200 resize-none h-24 focus:outline-none focus:ring-1 focus:ring-red-500 placeholder:text-slate-600"
          placeholder='e.g. "too saturated", "wrong garment", "wrong pose"'
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          disabled={submitting}
        />

        {error && <p className="text-xs text-red-400">{error}</p>}

        <div className="flex gap-2">
          <button
            className="flex-1 bg-red-600 hover:bg-red-500 disabled:opacity-40 text-white text-sm rounded-md py-2 transition-colors"
            disabled={submitting || !reason.trim()}
            onClick={handleReject}
          >
            {submitting ? "Saving…" : "Reject & Remember"}
          </button>
          <button
            className="px-4 bg-surface border border-border hover:border-slate-500 text-slate-300 text-sm rounded-md py-2 transition-colors"
            disabled={submitting}
            onClick={onClose}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
