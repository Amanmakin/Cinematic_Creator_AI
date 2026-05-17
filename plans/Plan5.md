# Plan 5 — Three.js Viewport + Scene Graph parity + Operational Transformations

> Status: **Not started**
> Depends on: Plan2 (HTTP/WS surface), Plan4 (real .glb to render)
> Unblocks: Plan6

## Integration with the LangGraph orchestrator

OT commits from the FE no longer mutate a hand-rolled scene graph — they mutate `AgentState.scene_graph` via `graph.update_state(config, values={"scene_graph": new_dsl}, as_node="scene_graph_generator")`. This:
- Reuses LangGraph's checkpointing — every drag of a camera slider is a new checkpoint, fully time-travelable.
- Reuses Plan1's lock enforcement — OT commits that touch locked paths get rejected in the same code path as LLM-generated mutations.
- The Timeline strip in the FE reads LangGraph's checkpoint history (`graph.get_state_history(config)`) instead of a separate event log.

"Forking" is `POST /projects/{id}/fork` from Plan2 — it derives a new `thread_id` from the chosen checkpoint id.

## Goal

Replace the placeholder Right Panel with a live React-Three-Fiber viewport that mirrors the backend scene exactly. Edits in the viewport propagate as Operational Transformations over WebSocket, applied to the canonical state in the backend, and rebroadcast — with locked paths refusing mutations.

## Deliverables

### D1. R3F viewport
- `apps/web/components/RenderStudio/Viewport.tsx`:
  - `<Canvas>` with `OrbitControls`, default lights replaced by lights from the scene graph.
  - `<GltfScene url={...} />` using `useGLTF` from `@react-three/drei`. Suspense fallback shows a wireframe stub.
  - Camera, lights, and animation tracks driven by `SceneGraph` JSON, not the glb extras (glb is geometry-only; parameters are the JSON overlay).
- `apps/web/components/RenderStudio/ControlsOverlay.tsx`:
  - Camera dolly slider (writes `scene.camera.position.z`).
  - Per-light intensity sliders.
  - Lens dropdown (24mm/35mm/50mm/85mm) → writes `scene.camera.focal_mm`.
  - All sliders dispatch `OtCommit` on debounced change (100ms).

### D2. Unified Scene Graph reader
- `apps/web/lib/sceneGraph/applyToR3F.ts` — pure function: `(graph: SceneGraph, three: { scene, camera, lights[] }) => void`. Idempotent; called whenever the store version increments.
- Same `SceneGraph` schema as the backend (from `packages/schemas/ts/index.d.ts`). FE never derives a parallel representation — it reads the canonical one.

### D3. Operational Transformations
- `OtCommit` event:
  ```ts
  type OtCommit = {
    project_id: string
    base_version: number          // last server-confirmed version FE saw
    ops: Array<
      | { op: "set", path: string, value: unknown }
      | { op: "insert", path: string, index: number, value: unknown }
      | { op: "delete", path: string }
    >
  }
  ```
- Backend (`apps/api/src/orchestrator/ot.py`):
  - Applies ops in order to a *deep copy* of current `SceneGraph`.
  - Rejects entire commit if any op targets a locked path → `OtCommitRejected` (reason: `LockedPathViolation`).
  - On stale `base_version`: rebases — if no op-vs-op path overlap, accept and emit `OtCommitRebased`. If overlap, reject with `OtConflict` and FE re-fetches.
  - On success: emit `SceneGraphMutated` DAG event with ops + new version. Reducer applies ops to the in-memory graph.
- Backend broadcasts the canonical updated `SceneGraph` (or just the new version + delta) to all connected sockets.

### D4. Reversibility UI
- `apps/web/components/ControlPanel/Timeline.tsx`:
  - Horizontal strip of DAG events for this project, filtered to `SceneGraphMutated` and `LayerGenerated` kinds.
  - Click a node → POST `/projects/{id}/fork` with `event_id` → backend moves the head pointer (no recomputation), broadcasts `Snapshot` to all connected sockets.
- Branching creates a new `head_pointer` row; the original branch is still walkable.

## Critical files to create

```
apps/web/components/RenderStudio/Viewport.tsx
apps/web/components/RenderStudio/GltfScene.tsx
apps/web/components/RenderStudio/ControlsOverlay.tsx
apps/web/components/RenderStudio/CameraRig.tsx
apps/web/components/ControlPanel/Timeline.tsx
apps/web/lib/sceneGraph/applyToR3F.ts
apps/web/lib/sceneGraph/diff.ts                 # produces minimal ops from before/after
apps/web/lib/ot/sendCommit.ts
apps/api/src/orchestrator/ot.py
apps/api/src/orchestrator/scene_graph_path.py    # JSON-pointer-ish path resolver
apps/api/src/routes/ot.py                        # POST /projects/{id}/ot
apps/api/src/routes/fork.py                      # POST /projects/{id}/fork
apps/api/tests/test_ot_conflicts.py
apps/api/tests/test_fork_pointer.py
```

Extend:
- `apps/api/src/dag/reducers.py` — `SceneGraphMutated`, `OtCommitRejected`, `OtConflict`, `Forked`.
- `apps/web/state/projectStore.ts` — add `sceneGraph`, `version`, `applyOt(ops)`, `forkTo(eventId)`.

## Dependencies (new packages)

- `@react-three/fiber`, `@react-three/drei`, `three` — frontend.
- No new backend deps (uses stdlib `json` for pointer ops).

## Verification

1. **Live update**: drag the camera dolly slider → backend receives `OtCommit`, applies, broadcasts. Second browser tab on same project sees the camera move within 200ms.
2. **Disjoint concurrent edits**: tab A drags camera, tab B adjusts a light at the same instant → both commits land, both tabs converge to the same final state.
3. **Conflict**: tab A and tab B both edit `camera.focal_mm` with the same `base_version` → server applies the first, rejects the second with `OtConflict`; tab B fetches and retries.
4. **Locked path refused**: lock `lights[0].intensity`, try to drag its slider → server rejects with `LockedPathViolation`, FE shows a toast.
5. **Fork**: click a DAG node from 5 minutes ago in the Timeline → viewport snaps to that scene state, zero LLM calls, zero Replicate calls (verify via network panel and logs).

## Out of scope

- Streaming preview frames into the viewport (Plan6).
- Embedded video playback (Plan6).
- Multi-user cursors / presence indicators (future).
