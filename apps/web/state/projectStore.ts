import { create } from "zustand";
import * as api from "@/lib/api";
import { createProjectSocket } from "@/lib/ws";
import type { AgentState, ProjectCanon, StateCheckpoint } from "@/lib/types/agentState";

interface TimelineEntry {
  checkpoint_id: string;
  execution_status: AgentState["execution_status"];
  timestamp: string;
}

interface ProjectState {
  projectId: string | null;
  canon: ProjectCanon | null;
  agentState: AgentState | null;
  timeline: TimelineEntry[];
  wsConnected: boolean;
  isRunning: boolean;
  error: string | null;

  // Actions
  initProject: (canon: ProjectCanon) => Promise<void>;
  setProjectId: (id: string) => void;
  connect: () => void;
  submitPrompt: (prompt: string) => Promise<void>;
  approve: (
    decision: "accept" | "modify" | "select_variant",
    opts?: { modified_prompt?: string; variant_index?: number },
  ) => Promise<void>;
  addLock: (path: string, reason: string, asset_id?: string) => Promise<void>;
  removeLock: (path: string) => Promise<void>;
  forkTo: (checkpointId: string) => Promise<void>;
}

let _destroyWs: (() => void) | null = null;

export const useProjectStore = create<ProjectState>((set, get) => ({
  projectId: null,
  canon: null,
  agentState: null,
  timeline: [],
  wsConnected: false,
  isRunning: false,
  error: null,

  initProject: async (canon) => {
    try {
      const { project_id } = await api.createProject(canon);
      set({ projectId: project_id, canon, error: null });
      get().connect();
    } catch (e: any) {
      set({ error: e.message });
    }
  },

  setProjectId: (id) => {
    set({ projectId: id });
    get().connect();
  },

  connect: () => {
    const { projectId } = get();
    if (!projectId) return;
    _destroyWs?.();
    _destroyWs = createProjectSocket(
      projectId,
      (msg) => {
        const state = msg.data as AgentState;
        set((prev) => ({
          agentState: { ...prev.agentState, ...state } as AgentState,
          timeline: [
            ...prev.timeline,
            {
              checkpoint_id: crypto.randomUUID(),
              execution_status: state.execution_status,
              timestamp: new Date().toISOString(),
            },
          ],
        }));
      },
      (open) => set({ wsConnected: open }),
    );
  },

  submitPrompt: async (prompt) => {
    const { projectId } = get();
    if (!projectId) return;
    set({ isRunning: true, error: null });
    try {
      await api.submitRun(projectId, prompt, (chunk) => {
        set((prev) => ({
          agentState: { ...prev.agentState, ...chunk } as AgentState,
        }));
      });
    } catch (e: any) {
      set({ error: e.message });
    } finally {
      set({ isRunning: false });
    }
  },

  approve: async (decision, opts) => {
    const { projectId } = get();
    if (!projectId) return;
    set({ isRunning: true, error: null });
    try {
      await api.approve(projectId, decision, opts, (chunk) => {
        set((prev) => ({
          agentState: { ...prev.agentState, ...chunk } as AgentState,
        }));
      });
    } catch (e: any) {
      set({ error: e.message });
    } finally {
      set({ isRunning: false });
    }
  },

  addLock: async (path, reason, asset_id) => {
    const { projectId } = get();
    if (!projectId) return;
    await api.addLock(projectId, { path, reason, asset_id });
    // Refresh lock list via agentState on next run; no local patch needed
  },

  removeLock: async (path) => {
    const { projectId } = get();
    if (!projectId) return;
    await api.deleteLock(projectId, path);
    set((prev) => ({
      agentState: prev.agentState
        ? {
            ...prev.agentState,
            semantic_locks: prev.agentState.semantic_locks.filter((l) => l.path !== path),
          }
        : null,
    }));
  },

  forkTo: async (checkpointId) => {
    const { projectId } = get();
    if (!projectId) return;
    const { fork_project_id } = await api.forkProject(projectId, checkpointId);
    set({ projectId: fork_project_id, agentState: null, timeline: [], error: null });
    get().connect();
  },
}));
