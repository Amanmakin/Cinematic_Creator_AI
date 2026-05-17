import type { AgentState, ProjectCanon, SemanticLock } from "./types/agentState";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface ProjectCreated {
  project_id: string;
  canon: ProjectCanon;
}

export async function createProject(canon: ProjectCanon): Promise<ProjectCreated> {
  const res = await fetch(`${BASE}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ canon }),
  });
  if (!res.ok) throw new Error(`createProject failed: ${res.status}`);
  return res.json();
}

export async function getProject(projectId: string) {
  const res = await fetch(`${BASE}/projects/${projectId}`);
  if (!res.ok) throw new Error(`getProject failed: ${res.status}`);
  return res.json();
}

/**
 * Submit a prompt and consume the SSE stream, calling `onChunk` for each state event.
 * Returns when the stream closes.
 */
export async function submitRun(
  projectId: string,
  userPrompt: string,
  onChunk: (state: Partial<AgentState>) => void,
): Promise<void> {
  const res = await fetch(`${BASE}/projects/${projectId}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ user_prompt: userPrompt }),
  });
  if (!res.ok) throw new Error(`submitRun failed: ${res.status}`);
  await consumeSse(res, onChunk);
}

export async function approve(
  projectId: string,
  decision: "accept" | "modify" | "select_variant",
  opts?: { modified_prompt?: string; variant_index?: number },
  onChunk?: (state: Partial<AgentState>) => void,
): Promise<void> {
  const res = await fetch(`${BASE}/projects/${projectId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ decision, ...opts }),
  });
  if (!res.ok) throw new Error(`approve failed: ${res.status}`);
  if (onChunk) await consumeSse(res, onChunk);
}

export async function getLocks(projectId: string) {
  const res = await fetch(`${BASE}/projects/${projectId}/locks`);
  if (!res.ok) throw new Error(`getLocks failed: ${res.status}`);
  return res.json() as Promise<(SemanticLock & { id: string; created_at: string })[]>;
}

export async function addLock(
  projectId: string,
  lock: { path: string; asset_id?: string; reason: string },
) {
  const res = await fetch(`${BASE}/projects/${projectId}/locks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(lock),
  });
  if (!res.ok) throw new Error(`addLock failed: ${res.status}`);
  return res.json();
}

export async function deleteLock(projectId: string, lockPath: string) {
  const res = await fetch(`${BASE}/projects/${projectId}/locks/${encodeURIComponent(lockPath)}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 204) throw new Error(`deleteLock failed: ${res.status}`);
}

export async function forkProject(projectId: string, checkpointId: string) {
  const res = await fetch(`${BASE}/projects/${projectId}/fork`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ checkpoint_id: checkpointId }),
  });
  if (!res.ok) throw new Error(`fork failed: ${res.status}`);
  return res.json() as Promise<{ fork_project_id: string; source_checkpoint_id: string }>;
}

export async function listCheckpoints(projectId: string) {
  const res = await fetch(`${BASE}/projects/${projectId}/checkpoints`);
  if (!res.ok) throw new Error(`listCheckpoints failed: ${res.status}`);
  return res.json();
}

export async function submitOt(
  projectId: string,
  baseVersion: number,
  ops: Array<{ op: string; path: string; value?: unknown; index?: number }>,
) {
  const res = await fetch(`${BASE}/projects/${projectId}/ot`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ base_version: baseVersion, ops }),
  });
  if (res.status === 409) {
    const body = await res.json();
    throw Object.assign(new Error(body.detail ?? "OT conflict"), { status: 409, body });
  }
  if (!res.ok) throw new Error(`submitOt failed: ${res.status}`);
  return res.json() as Promise<{ version: number; status: string }>;
}

async function consumeSse(
  res: Response,
  onChunk: (state: Partial<AgentState>) => void,
): Promise<void> {
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    let event = "";
    let data = "";
    for (const line of lines) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data = line.slice(5).trim();
      else if (line === "" && data) {
        if (event === "state") onChunk(JSON.parse(data));
        event = "";
        data = "";
      }
    }
  }
}
