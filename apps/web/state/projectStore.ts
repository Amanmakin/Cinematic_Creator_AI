import { create } from "zustand";
import * as api from "@/lib/api";
import type { ApproveDecision, ApproveOpts } from "@/lib/api";
import { createProjectSocket } from "@/lib/ws";
import { diffSceneGraph } from "@/lib/sceneGraph/diff";
import type { AgentState, BlenderDsl, ProjectCanon, StateCheckpoint } from "@/lib/types/agentState";
import type { OtOp } from "@/lib/sceneGraph/diff";

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
  otSceneGraph: BlenderDsl | null;
  otVersion: number;
  wsConnected: boolean;
  isRunning: boolean;
  error: string | null;

  // Actions
  initProject: (canon: ProjectCanon) => Promise<void>;
  setProjectId: (id: string) => void;
  connect: () => void;
  submitPrompt: (prompt: string, sampleImageUrls?: string[]) => Promise<void>;
  approve: (decision: ApproveDecision, opts?: ApproveOpts) => Promise<void>;
  addLock: (path: string, reason: string, asset_id?: string) => Promise<void>;
  removeLock: (path: string) => Promise<void>;
  forkTo: (checkpointId: string) => Promise<void>;
  applyOt: (ops: OtOp[]) => Promise<void>;
}

const PROJECT_ID_KEY = "cvc_project_id";

function saveProjectId(id: string) {
  if (typeof window !== "undefined") localStorage.setItem(PROJECT_ID_KEY, id);
}

let _destroyWs: (() => void) | null = null;

export const useProjectStore = create<ProjectState>((set, get) => ({
  projectId: null,
  canon: null,
  agentState: null,
  timeline: [],
  otSceneGraph: null,
  otVersion: 0,
  wsConnected: false,
  isRunning: false,
  error: null,

  initProject: async (canon) => {
    try {
      const { project_id } = await api.createProject(canon);
      saveProjectId(project_id);
      set({ projectId: project_id, canon, error: null });
      get().connect();
    } catch (e: any) {
      set({ error: e.message });
    }
  },

  setProjectId: (id) => {
    saveProjectId(id);
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
        if (msg.type === "state") {
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
        } else if (msg.type === "scene_graph_mutated" || msg.type === "ot_commit_rebased") {
          const data = msg.data as { version: number; scene_graph: BlenderDsl };
          set({ otSceneGraph: data.scene_graph, otVersion: data.version });
        } else if (msg.type === "ot_commit_rejected") {
          const data = msg.data as { reason: string; path?: string };
          set({ error: `OT rejected: ${data.reason}${data.path ? ` (${data.path})` : ""}` });
        } else if (msg.type === "ot_conflict") {
          set({ error: "OT conflict — server state changed, re-fetching" });
        }
      },
      (open) => set({ wsConnected: open }),
    );
  },

  submitPrompt: async (prompt, sampleImageUrls) => {
    const { projectId } = get();
    if (!projectId) return;
    set({ isRunning: true, error: null });
    try {
      await api.submitRun(projectId, prompt, (chunk) => {
        set((prev) => ({
          agentState: { ...prev.agentState, ...chunk } as AgentState,
        }));
      }, sampleImageUrls);
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
    set({ projectId: fork_project_id, agentState: null, timeline: [], otSceneGraph: null, otVersion: 0, error: null });
    get().connect();
  },

  applyOt: async (ops) => {
    const { projectId, otVersion, otSceneGraph } = get();
    if (!projectId || !otSceneGraph) return;
    set({ error: null });
    try {
      await api.submitOt(projectId, otVersion, ops);
    } catch (e: any) {
      set({ error: e.message });
    }
  },
}));
