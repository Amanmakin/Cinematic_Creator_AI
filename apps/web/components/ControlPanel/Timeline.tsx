"use client";

import { useEffect, useState } from "react";
import { useProjectStore } from "@/state/projectStore";
import { listCheckpoints } from "@/lib/api";

interface Checkpoint {
  checkpoint_id: string;
  execution_status: string;
  has_scene_graph: boolean;
  created_at: string | null;
  kind: "SceneGraphMutated" | "AgentStep";
}

const KIND_COLOR: Record<string, string> = {
  SceneGraphMutated: "bg-indigo-400",
  AgentStep: "bg-zinc-500",
};

const KIND_LABEL: Record<string, string> = {
  SceneGraphMutated: "Scene",
  AgentStep: "Step",
};

export default function Timeline() {
  const { projectId, forkTo } = useProjectStore();
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [forking, setForking] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    setLoading(true);
    listCheckpoints(projectId)
      .then((data) => setCheckpoints(data as Checkpoint[]))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectId]);

  if (!projectId) return null;

  async function handleFork(checkpointId: string) {
    setForking(checkpointId);
    try {
      await forkTo(checkpointId);
    } finally {
      setForking(null);
    }
  }

  const scenePoints = checkpoints.filter((c) => c.kind === "SceneGraphMutated");
  const displayPoints = scenePoints.length > 0 ? scenePoints : checkpoints.slice(0, 10);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">Timeline</span>
        {loading && <span className="text-[10px] text-zinc-500">loading…</span>}
      </div>

      {displayPoints.length === 0 && !loading && (
        <p className="text-xs text-zinc-500 italic">No checkpoints yet.</p>
      )}

      <div className="flex items-center gap-1 overflow-x-auto pb-1">
        {displayPoints.map((cp, i) => (
          <button
            key={cp.checkpoint_id}
            title={`${cp.kind} · ${cp.execution_status}\n${cp.created_at ?? ""}${"\n"}Click to fork to this point`}
            disabled={forking !== null}
            onClick={() => handleFork(cp.checkpoint_id)}
            className={`flex-shrink-0 flex flex-col items-center gap-1 group`}
          >
            <div
              className={`w-3 h-3 rounded-full ${KIND_COLOR[cp.kind] ?? "bg-zinc-500"} group-hover:ring-2 ring-indigo-400 transition-all ${
                forking === cp.checkpoint_id ? "animate-pulse" : ""
              }`}
            />
            <span className="text-[8px] text-zinc-500 group-hover:text-zinc-300">
              {i + 1}
            </span>
          </button>
        ))}
      </div>

      <p className="text-[10px] text-zinc-500">
        Click a dot to fork the project to that checkpoint — zero LLM/render calls.
      </p>
    </div>
  );
}
