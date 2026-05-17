# Plan 6 — Render Orchestrator + Preview/Final pipeline

> Status: **Not started**
> Depends on: Plan3 (Replicate adapter), Plan4 (DSL + Blender runner), Plan5 (viewport to stream into)
> Unblocks: end-to-end demo

## Integration with the LangGraph orchestrator

LangGraph runs are **short and synchronous** — they produce a validated `BlenderDsl`. The actual long-running visual generation and Blender renders run **outside the graph** as arq tasks:
- After `execution_status="completed"`, the FastAPI surface enqueues `render_preview(scene_hash)` to arq.
- After user approval, `render_final` is enqueued.
- Adapter calls inside Plan3's `visual_generator` node also defer to arq when batch size > 1 — the node awaits a `gather()` over a list of arq jobs.

The `BudgetLedger` is a separate SQLite store keyed by `project_id`; it gates `arq` task entry, not LangGraph nodes (so the engine itself stays cheap and fast).

## Goal

A gated, budgeted, cancellable execution pipeline. Visual generation, validation, and render run as queued tasks; preview frames stream live to the viewport; final render is hard-gated behind explicit user approval; failures degrade cleanly.

## Deliverables

### D1. Task queue (arq + Redis)
- `docker-compose.yml` at repo root with a single `redis:7-alpine` service. Local-first: `docker compose up redis` is the only infra step.
- `apps/api/src/queue/worker.py` — `arq` worker definition. Queues:
  - `visual` — Replicate / ComfyUI calls (concurrency 4 default, configurable).
  - `render` — Blender subprocess (concurrency 1; Blender is heavy).
  - `validate` — physical validation + DSL compile (concurrency 8).
- `apps/api/src/queue/dispatch.py` — `enqueue(task_name, project_id, dag_node_id, payload, budget_token)`. Records a `TaskEnqueued` DAG event including the arq job id so cancellation can find it.
- Each task carries a `budget_token` issued by `BudgetLedger.reserve(estimate)`; on success → `commit`, on failure → `refund`.

### D2. Concurrency isolation
- Per-project max-in-flight enforced via Redis `INCR`/`DECR` on a `proj:{id}:inflight` key (default cap 4). Over-limit enqueues are queued in arq but blocked at task entry with `asyncio.wait_for` on a semaphore.
- Cancellation cascade: cancelling a parent DAG node walks descendants, calls `arq.cancel(job_id)` on each task, escalates Blender subprocesses with SIGTERM → SIGKILL.

### D3. Preview render (streamed)
- `workers/render/render.py` extended to render a frame sequence at low res (e.g. 480×854 for 9:16) and write each PNG to `projects/{id}/renders/{scene_hash}/preview/frame_{n:04}.png`.
- After each frame, the runner emits a `PreviewFrameReady` DAG event with `{frame_index, total, path}`. WS broadcaster fans this out.
- FE `apps/web/components/RenderStudio/PreviewStream.tsx`:
  - Subscribes to `PreviewFrameReady` events.
  - Fetches each frame via `GET /projects/{id}/renders/{scene_hash}/preview/{n}` and swaps into a `<canvas>` at the scene FPS.
  - Toggleable between the live R3F viewport (Plan5) and the rendered preview.

### D4. Hard approval checkpoint
- `FinalRenderRequested` event includes `scene_hash`.
- The `render_final` task **first** checks the DAG for a `FinalRenderApproved` event whose `scene_hash` matches; if absent, refuses and emits `FinalRenderBlocked`.
- FE `ApprovalDialog` (from Plan2) handles `mode: "final_render"` — shows the preview alongside the budget impact, click-through approves.

### D5. Final render → mp4
- `workers/render/render.py` extended with a `--mode final` flag:
  - Cycles if available and canon requests high quality, else EEVEE.
  - Resolution and FPS from the DSL `scene`.
  - Output: PNG sequence → ffmpeg encode to `projects/{id}/out/{scene_hash}.mp4` (H.264, yuv420p, crf 18).
- FFmpeg invoked via subprocess; failure surfaces as `EncodingFailed`.

### D6. Failure recovery
- `RenderFailed` includes a structured `cause: Literal["timeout","subprocess_error","encoding_failed","budget","provider_unavailable"]` and a free-form `details` string.
- Orchestrator marks all DAG nodes downstream of the failed node `stale` (a flag on the reducer state, not an event mutation).
- `max_retries = 2` enforced in `dispatch.enqueue`; further enqueues for the same `(project_id, dag_node_id)` are refused until a user-triggered `Retry` event clears the counter.

## Critical files to create

```
docker-compose.yml
apps/api/src/queue/__init__.py
apps/api/src/queue/worker.py
apps/api/src/queue/dispatch.py
apps/api/src/queue/tasks/visual.py        # wraps adapter.execute
apps/api/src/queue/tasks/render_preview.py
apps/api/src/queue/tasks/render_final.py
apps/api/src/queue/tasks/validate_dsl.py
apps/api/src/queue/cancellation.py
apps/api/src/routes/render.py             # POST .../preview, POST .../final
apps/api/src/routes/cancel.py
apps/api/tests/test_cancellation_cascade.py
apps/api/tests/test_budget_refund.py
apps/api/tests/test_max_retries.py
apps/web/components/RenderStudio/PreviewStream.tsx
apps/web/components/RenderStudio/ViewToggle.tsx
apps/web/components/ControlPanel/BudgetIndicator.tsx
apps/web/components/ControlPanel/RenderQueue.tsx
```

Extend:
- `apps/api/src/dag/reducers.py` — `TaskEnqueued`, `TaskStarted`, `TaskCancelled`, `PreviewFrameReady`, `PreviewCompleted`, `FinalRenderRequested`, `FinalRenderBlocked`, `FinalRenderApproved`, `FinalRenderCompleted`, `RenderFailed`, `EncodingFailed`.

## Dependencies

- `arq`, `redis` (Python), `pygltflib` (carried from Plan4).
- System: `ffmpeg` (Homebrew: `brew install ffmpeg`).
- `docker compose` for Redis.

## Verification

1. **End-to-end happy path**: from a fresh project, prompt → intent → storyboard → creative intents → assets in UAR → DSL compile → validation pass → preview render → user approves → final mp4 at `projects/{id}/out/{scene_hash}.mp4`. Plays back in QuickTime.
2. **Cancellation**: start a preview, click Cancel mid-render → Blender process receives SIGTERM within 2s, DAG node marked `Cancelled`, no zombie processes (`pgrep blender` empty), Redis `inflight` counter back to 0.
3. **Hard gate**: programmatically post `FinalRenderRequested` without an `Approved` event → task refuses to start, `FinalRenderBlocked` event in DAG.
4. **Retry cap**: mock Replicate to fail every call → 2 retries → `RenderFailed`, third enqueue refused with `MaxRetriesExceeded`; manual `Retry` event resets the counter.
5. **Budget refund**: budget ledger at 1000, enqueue a task estimated at 500 (reserved), task fails → refund returns ledger to 1000.
6. **Stream parity**: preview frames in FE play back at the scene's FPS, no dropped frames at 30fps for a 480×854 sequence.

## Out of scope

- Distributed workers across machines (single-host arq is enough for now).
- GPU-accelerated final render (no local GPU per constraints; revisit when remote workers come online).
- Realtime audio / score (future).
