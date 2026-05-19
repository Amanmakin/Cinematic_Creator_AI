"use client";

import { useEffect } from "react";
import ApprovalDialog from "@/components/ControlPanel/ApprovalDialog";
import BudgetIndicator from "@/components/ControlPanel/BudgetIndicator";
import LockManager from "@/components/ControlPanel/LockManager";
import PhaseStatusBar from "@/components/ControlPanel/PhaseStatusBar";
import PromptComposer from "@/components/ControlPanel/PromptComposer";
import Timeline from "@/components/ControlPanel/Timeline";
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

export default function WorkspacePage() {
  const { projectId, agentState, connect, initProject } = useProjectStore();

  useEffect(() => {
    if (projectId) {
      connect();
    } else {
      initProject(DEFAULT_CANON);
    }
  }, [projectId, connect, initProject]);

  const needsApproval =
    agentState?.execution_status === "awaiting_human_approval" ||
    agentState?.execution_status === "speculative_batching" ||
    agentState?.execution_status === "previsualization_generated" ||
    agentState?.execution_status === "model_generated";

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Left panel — elevated from bg for contrast */}
      <aside className="w-[420px] flex-shrink-0 flex flex-col gap-4 p-4 bg-zinc-900 border-r border-zinc-700/60 overflow-y-auto">
        <h1 className="text-lg font-semibold text-indigo-400 tracking-tight">AI Studio</h1>
        <PromptComposer />
        <PhaseStatusBar />
        <Timeline />
        <LockManager />
        <BudgetIndicator />
        {projectId && <SettingsDrawer projectId={projectId} />}
      </aside>

      {/* Right panel */}
      <main className="flex-1 overflow-auto bg-[#09090b]">
        <Viewport />
      </main>

      {needsApproval && <ApprovalDialog />}
    </div>
  );
}
