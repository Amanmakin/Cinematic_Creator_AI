/**
 * Produces a minimal set of OT ops from two BlenderDsl snapshots.
 *
 * Only tracks the fields the ControlsOverlay can mutate:
 *   scene.camera.*   scene.lights[n].*
 *
 * This is intentionally narrow — a full recursive differ is not needed.
 */

import type { BlenderDsl } from "@/lib/types/agentState";

export type SetOp = { op: "set"; path: string; value: unknown };
export type OtOp = SetOp;

function cameraOps(prev: BlenderDsl["scene"]["camera"], next: BlenderDsl["scene"]["camera"]): OtOp[] {
  const ops: OtOp[] = [];
  const base = "scene.camera";

  if (prev.focal_mm !== next.focal_mm) ops.push({ op: "set", path: `${base}.focal_mm`, value: next.focal_mm });
  if (prev.f_stop !== next.f_stop) ops.push({ op: "set", path: `${base}.f_stop`, value: next.f_stop });
  if (prev.sensor_mm !== next.sensor_mm) ops.push({ op: "set", path: `${base}.sensor_mm`, value: next.sensor_mm });

  const pos = prev.position;
  const npos = next.position;
  if (pos.x !== npos.x) ops.push({ op: "set", path: `${base}.position.x`, value: npos.x });
  if (pos.y !== npos.y) ops.push({ op: "set", path: `${base}.position.y`, value: npos.y });
  if (pos.z !== npos.z) ops.push({ op: "set", path: `${base}.position.z`, value: npos.z });

  const la = prev.look_at;
  const nla = next.look_at;
  if (la.x !== nla.x) ops.push({ op: "set", path: `${base}.look_at.x`, value: nla.x });
  if (la.y !== nla.y) ops.push({ op: "set", path: `${base}.look_at.y`, value: nla.y });
  if (la.z !== nla.z) ops.push({ op: "set", path: `${base}.look_at.z`, value: nla.z });

  return ops;
}

function lightOps(
  prevLights: BlenderDsl["scene"]["lights"],
  nextLights: BlenderDsl["scene"]["lights"],
): OtOp[] {
  const ops: OtOp[] = [];
  const len = Math.min(prevLights.length, nextLights.length);

  for (let i = 0; i < len; i++) {
    const p = prevLights[i];
    const n = nextLights[i];
    const base = `scene.lights[${i}]`;

    if (p.intensity !== n.intensity) ops.push({ op: "set", path: `${base}.intensity`, value: n.intensity });
    if (p.color_kelvin !== n.color_kelvin) ops.push({ op: "set", path: `${base}.color_kelvin`, value: n.color_kelvin });
    if (p.position.x !== n.position.x) ops.push({ op: "set", path: `${base}.position.x`, value: n.position.x });
    if (p.position.y !== n.position.y) ops.push({ op: "set", path: `${base}.position.y`, value: n.position.y });
    if (p.position.z !== n.position.z) ops.push({ op: "set", path: `${base}.position.z`, value: n.position.z });
  }

  return ops;
}

export function diffSceneGraph(prev: BlenderDsl, next: BlenderDsl): OtOp[] {
  return [
    ...cameraOps(prev.scene.camera, next.scene.camera),
    ...lightOps(prev.scene.lights, next.scene.lights),
  ];
}
