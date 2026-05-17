import type { AgentState, BlenderDsl } from "./types/agentState";

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";
const MAX_BACKOFF_MS = 5_000;

export type WsMessage =
  | { type: "state"; data: Partial<AgentState> }
  | { type: "scene_graph_mutated"; data: { version: number; scene_graph: BlenderDsl; ops: unknown[] } }
  | { type: "ot_commit_rebased"; data: { version: number; scene_graph: BlenderDsl; ops: unknown[] } }
  | { type: "ot_commit_rejected"; data: { reason: string; path?: string } }
  | { type: "ot_conflict"; data: Record<string, never> };

export function createProjectSocket(
  projectId: string,
  onMessage: (msg: WsMessage) => void,
  onStatusChange?: (open: boolean) => void,
): () => void {
  let ws: WebSocket | null = null;
  let attempt = 0;
  let destroyed = false;
  let pingTimer: ReturnType<typeof setInterval> | null = null;

  function connect() {
    if (destroyed) return;
    ws = new WebSocket(`${WS_BASE}/ws/project/${projectId}`);

    ws.onopen = () => {
      attempt = 0;
      onStatusChange?.(true);
      pingTimer = setInterval(() => ws?.readyState === WebSocket.OPEN && ws.send("ping"), 20_000);
    };

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data) as WsMessage;
        if (msg.type === "state") onMessage(msg);
      } catch {
        // ignore malformed frames
      }
    };

    ws.onclose = () => {
      if (pingTimer) clearInterval(pingTimer);
      onStatusChange?.(false);
      if (!destroyed) {
        const delay = Math.min(MAX_BACKOFF_MS, 200 * 2 ** attempt);
        attempt++;
        setTimeout(connect, delay);
      }
    };

    ws.onerror = () => ws?.close();
  }

  connect();

  return () => {
    destroyed = true;
    if (pingTimer) clearInterval(pingTimer);
    ws?.close();
  };
}
