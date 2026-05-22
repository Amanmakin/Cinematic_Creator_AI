"use client";

import { useEffect } from "react";
import ApprovalDialog from "@/components/ControlPanel/ApprovalDialog";
import PhaseStatusBar from "@/components/ControlPanel/PhaseStatusBar";
import PromptComposer from "@/components/ControlPanel/PromptComposer";
import Viewport from "@/components/RenderStudio/Viewport";
import { SettingsDrawer } from "@/components/SettingsDrawer";
import { useProjectStore } from "@/state/projectStore";
import type { ProjectCanon } from "@/lib/types/agentState";

const DEFAULT_CANON: ProjectCanon = {
  aspect_ratio: "16:9",
  duration_seconds_max: 30,
  aesthetic_tags: [],
  style_guide: "",
  banned_terms: [],
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function WorkspacePage() {
  const { projectId, agentState, connect, initProject, setProjectId } = useProjectStore();

  // Runs only on the client — safe to access localStorage here.
  useEffect(() => {
    const saved = localStorage.getItem("cvc_project_id");
    if (saved) {
      setProjectId(saved); // restores ID → triggers connect()
    } else {
      initProject(DEFAULT_CANON); // first-ever load → creates project
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const needsApproval =
    agentState?.execution_status === "awaiting_human_approval" ||
    agentState?.execution_status === "speculative_batching" ||
    agentState?.execution_status === "previsualization_generated" ||
    agentState?.execution_status === "model_generated";

  // Once the gltf_assembler node runs, agentState carries the URL path.
  // Convert it to a full URL so Viewport can load it in Three.js.
  const glbUrl = agentState?.gltf_assembled_path
    ? `${API_BASE}${agentState.gltf_assembled_path}`
    : null;

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Left panel — elevated from bg for contrast */}
      <aside className="w-[420px] flex-shrink-0 flex flex-col gap-4 p-4 bg-zinc-900 border-r border-zinc-700/60 overflow-y-auto">
        <h1 className="text-lg font-semibold text-indigo-400 tracking-tight">AI Studio</h1>
        <PromptComposer />
        <PhaseStatusBar />
        {projectId && <SettingsDrawer projectId={projectId} />}
      </aside>

      {/* Right panel */}
      <main className="flex-1 overflow-auto bg-[#09090b]">
        <Viewport glbUrl={glbUrl} />
      </main>

      {needsApproval && <ApprovalDialog />}
    </div>
  );
}
