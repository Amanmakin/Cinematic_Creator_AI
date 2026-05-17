"use client";

import { useEffect, useState } from "react";

interface QueueEntry {
  job_id: string;
  dag_node_id: string;
  scene_hash: string;
  status: "queued" | "rendering" | "completed" | "failed" | "cancelled";
  kind: "preview" | "final";
}

interface RenderQueueProps {
  projectId: string;
  onCancel?: (dagNodeId: string) => void;
}

export default function RenderQueue({ projectId, onCancel }: RenderQueueProps) {
  const [entries, setEntries] = useState<QueueEntry[]>([]);

  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8000/ws/project/${projectId}`);
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string);
        if (msg.kind === "TaskEnqueued") {
          setEntries((prev) => [
            ...prev.filter((e) => e.job_id !== msg.job_id),
            {
              job_id: msg.job_id ?? "",
              dag_node_id: msg.dag_node_id ?? "",
              scene_hash: msg.scene_hash ?? "",
              status: "queued",
              kind: msg.task_name?.includes("final") ? "final" : "preview",
            },
          ]);
        } else if (msg.kind === "TaskStarted") {
          setEntries((prev) =>
            prev.map((e) =>
              e.dag_node_id === msg.dag_node_id ? { ...e, status: "rendering" } : e
            )
          );
        } else if (msg.kind === "PreviewCompleted" || msg.kind === "FinalRenderCompleted") {
          setEntries((prev) =>
            prev.map((e) =>
              e.scene_hash === msg.scene_hash ? { ...e, status: "completed" } : e
            )
          );
        } else if (msg.kind === "RenderFailed" || msg.kind === "EncodingFailed") {
          setEntries((prev) =>
            prev.map((e) =>
              e.scene_hash === msg.scene_hash ? { ...e, status: "failed" } : e
            )
          );
        } else if (msg.kind === "TaskCancelled") {
          setEntries((prev) =>
            prev.map((e) =>
              e.dag_node_id === msg.dag_node_id ? { ...e, status: "cancelled" } : e
            )
          );
        }
      } catch {
        // ignore
      }
    };
    return () => ws.close();
  }, [projectId]);

  if (entries.length === 0) return null;

  const statusColor: Record<QueueEntry["status"], string> = {
    queued: "text-slate-400",
    rendering: "text-yellow-400",
    completed: "text-green-400",
    failed: "text-red-400",
    cancelled: "text-slate-600",
  };

  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-slate-400 uppercase tracking-wide">
        Render Queue
      </label>
      <div className="flex flex-col gap-1 max-h-40 overflow-y-auto">
        {entries.map((e) => (
          <div
            key={e.job_id}
            className="flex items-center justify-between bg-surface border border-border rounded px-2 py-1 text-xs"
          >
            <span className="text-slate-300 truncate max-w-[120px]">
              {e.kind === "final" ? "Final" : "Preview"} — {e.scene_hash.slice(0, 8)}
            </span>
            <div className="flex items-center gap-2">
              <span className={statusColor[e.status]}>{e.status}</span>
              {(e.status === "queued" || e.status === "rendering") && onCancel && (
                <button
                  className="text-slate-500 hover:text-red-400 transition-colors"
                  onClick={() => onCancel(e.dag_node_id)}
                  title="Cancel"
                >
                  ✕
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
