"use client";

import { useEffect } from "react";
import ApprovalDialog from "@/components/ControlPanel/ApprovalDialog";
import BudgetIndicator from "@/components/ControlPanel/BudgetIndicator";
import LockManager from "@/components/ControlPanel/LockManager";
import PromptComposer from "@/components/ControlPanel/PromptComposer";
import StateTimeline from "@/components/ControlPanel/StateTimeline";
import JsonTree from "@/components/RenderStudio/JsonTree";
import { useProjectStore } from "@/state/projectStore";

export default function WorkspacePage() {
  const { projectId, agentState, connect } = useProjectStore();

  useEffect(() => {
    if (projectId) connect();
  }, [projectId, connect]);

  const needsApproval =
    agentState?.execution_status === "awaiting_human_approval" ||
    agentState?.execution_status === "speculative_batching";

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Left panel */}
      <aside className="w-[420px] flex-shrink-0 flex flex-col gap-4 p-4 bg-panel border-r border-border overflow-y-auto">
        <h1 className="text-lg font-semibold text-accent">CinematicVideoCreator</h1>
        <PromptComposer />
        <StateTimeline />
        <LockManager />
        <BudgetIndicator />
      </aside>

      {/* Right panel */}
      <main className="flex-1 overflow-auto p-6">
        <h2 className="text-sm font-medium text-slate-400 mb-3">Render Studio (DSL Preview)</h2>
        <JsonTree data={agentState?.scene_graph ?? null} />
      </main>

      {needsApproval && <ApprovalDialog />}
    </div>
  );
}
