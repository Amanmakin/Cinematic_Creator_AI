/**
 * Sends an OtCommit to the backend via HTTP POST.
 *
 * The server applies the commit, increments the version, and broadcasts
 * a 'scene_graph_mutated' (or 'ot_commit_rebased') WS event to all
 * connected clients — including the sender. The store's WS handler picks
 * this up and updates sceneGraph + version.
 */

import type { OtOp } from "@/lib/sceneGraph/diff";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type OtCommit = {
  project_id: string;
  base_version: number;
  ops: OtOp[];
};

export type OtCommitResult =
  | { ok: true; version: number; status: "accepted" | "rebased" }
  | { ok: false; reason: "LockedPathViolation"; path: string }
  | { ok: false; reason: "OtConflict" }
  | { ok: false; reason: "NetworkError"; message: string };

export async function sendCommit(commit: OtCommit): Promise<OtCommitResult> {
  try {
    const res = await fetch(`${BASE}/projects/${commit.project_id}/ot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ base_version: commit.base_version, ops: commit.ops }),
    });

    if (res.ok) {
      const body = await res.json();
      return { ok: true, version: body.version, status: body.status };
    }

    if (res.status === 409) {
      const body = await res.json();
      const detail: string = body.detail ?? "";
      if (detail.startsWith("Locked path:")) {
        return { ok: false, reason: "LockedPathViolation", path: detail.replace("Locked path: ", "") };
      }
      return { ok: false, reason: "OtConflict" };
    }

    return { ok: false, reason: "NetworkError", message: `HTTP ${res.status}` };
  } catch (e: unknown) {
    return { ok: false, reason: "NetworkError", message: String(e) };
  }
}
