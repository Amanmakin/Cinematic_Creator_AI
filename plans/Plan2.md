# Plan 2 — HTTP Surface + Next.js Workspace Shell

> Status: **Not started**
> Depends on: Plan1 (the LangGraph engine must run end-to-end before being wrapped)
> Unblocks: Plan3, Plan5

## Goal

Expose the Plan1 LangGraph engine over HTTP and stream its state transitions to a Next.js two-panel workspace. Add canonical persistence for `ProjectCanon`, lock CRUD, and an approval flow that resolves the `human_approval`/`speculative` interrupts surfaced by the engine.

## Why this changed from the original Plan2

The original Plan2 implemented the Intent Validator + Storyboard generator + Semantic Locker as standalone orchestrator modules. Those now live as **LangGraph nodes inside Plan1**. Plan2 is now purely the **surface layer** around that engine — HTTP, persistence, streaming, and the FE shell.

## Deliverables

### D1. FastAPI wrapper (`apps/api/`)
- New package alongside `apps/orchestrator`. Imports `orchestrator.graph.build_graph()` and `orchestrator.state.AgentState`.
- Endpoints:
  - `POST /projects` — creates project, persists immutable `ProjectCanon`, returns `project_id`.
  - `GET /projects/{id}` — returns the latest checkpointed `AgentState` for the project's `thread_id`.
  - `POST /projects/{id}/runs` — body: `{user_prompt}`. Invokes the graph with `thread_id=project_id`, streams state updates via SSE or WS.
  - `POST /projects/{id}/approve` — body: `{decision: "accept"|"modify"|"select_variant", variant_index?}`. Resumes the graph at the interrupt by calling `graph.update_state(...)` + `graph.invoke(None, ...)`.
  - `POST /projects/{id}/locks` / `DELETE /projects/{id}/locks/{path}` — CRUD against a `locks` table; locks injected into `AgentState.semantic_locks` on next run.
  - `POST /projects/{id}/fork` — body: `{checkpoint_id}`. Forks the LangGraph thread (via a derived `thread_id`) so a user can branch off any prior checkpoint.
- WebSocket `/ws/project/{id}` mirrors LangGraph streaming events to FE: `{type: "state", data: AgentState}` per node completion.

### D2. Canon + lock persistence
- SQLite (`projects.sqlite`) — small, only persists what LangGraph's `MemorySaver` doesn't:
  - `projects(id, created_at, canon_json)` — canon immutable after first write.
  - `locks(project_id, path, asset_id, reason, created_at)` — feeds `AgentState.semantic_locks` at run-time.
- `MemorySaver` itself is upgraded to `SqliteSaver` from `langgraph.checkpoint.sqlite` so checkpoints persist across restarts — the engine's time-travel survives process death.

### D3. Next.js workspace shell (`apps/web/`)
- Next.js 14 (App Router) + Tailwind + Zustand.
- Two-panel layout:
  - **Left Panel — Control & Context**
    - `PromptComposer.tsx` — submits to `POST /projects/{id}/runs`.
    - `StateTimeline.tsx` — vertical list of LangGraph node completions; clicking a row calls `POST /fork` with that checkpoint id.
    - `ApprovalDialog.tsx` — opens automatically when a `human_approval` or `speculative` interrupt fires; presents either accept/modify (high ambiguity) or a 2–3 variant chooser (medium).
    - `LockManager.tsx` — list of `semantic_locks` with delete buttons + an "Add lock" form.
    - `BudgetIndicator.tsx` — stub for Plan3.
  - **Right Panel — Render Studio (Placeholder)**
    - Renders the current `BlenderDsl` as a JSON tree (read-only) until Plan5 ships the real R3F viewport.
- Zustand store `state/projectStore.ts`: `projectId`, `agentState`, `connect()`, `submitPrompt()`, `approve()`, `addLock()`, `forkTo()`.
- WS client `lib/ws.ts` with exponential backoff reconnect (cap 5s).

### D4. Schema parity
- TypeScript types generated from Pydantic models in `apps/orchestrator/src/orchestrator/state.py` and `schemas/*.py` via `pydantic-to-typescript` (or `datamodel-code-generator --output-model-type ...`).
- `pnpm build:schemas` regenerates `apps/web/lib/types/agentState.d.ts`. CI fails on drift.

### D5. Speculative variant resolution
- When the engine emits `execution_status="speculative_batching"`, the API surfaces `state.speculative_variants` to FE. User picks one → `POST /approve` with `{decision: "select_variant", variant_index}` → API calls `graph.update_state(config, values={"scene_graph": variants[i], "speculative_variants": []}, as_node="speculative_batcher")` and resumes — the resumed run picks up at `physical_validation`.

## Critical files to create

```
apps/api/pyproject.toml
apps/api/src/api/__init__.py
apps/api/src/api/main.py
apps/api/src/api/settings.py
apps/api/src/api/routes/projects.py
apps/api/src/api/routes/runs.py
apps/api/src/api/routes/approvals.py
apps/api/src/api/routes/locks.py
apps/api/src/api/routes/forks.py
apps/api/src/api/ws/broadcaster.py
apps/api/src/api/persistence/projects_db.py
apps/api/tests/test_runs_streaming.py
apps/api/tests/test_approval_resume.py
apps/web/package.json
apps/web/next.config.mjs
apps/web/tailwind.config.ts
apps/web/app/layout.tsx
apps/web/app/(workspace)/page.tsx
apps/web/components/ControlPanel/{PromptComposer,StateTimeline,ApprovalDialog,LockManager,BudgetIndicator}.tsx
apps/web/components/RenderStudio/JsonTree.tsx
apps/web/lib/ws.ts
apps/web/lib/api.ts
apps/web/state/projectStore.ts
```

## Verification

1. Submit a prompt via FE → LangGraph runs in api → state stream renders each node completion in the StateTimeline within 200ms of the engine emitting it.
2. Tweak the prompt to be highly ambiguous → `ApprovalDialog` opens for human approval; user clicks Accept → run resumes and completes.
3. Run a medium-ambiguity prompt → `speculative_batcher` emits 3 variants → user picks variant B → engine resumes, validates, completes; final `scene_graph` matches variant B.
4. Add a lock on `scene.camera.focal_mm = 50`, resubmit the same prompt → generator output preserves that field; lock violation forces retry as in Plan1.
5. Restart the api → previous run state survives (SqliteSaver), FE reconnects, timeline shows prior checkpoints.

## Out of scope

- Real R3F viewport (Plan5).
- Visual generation / Replicate (Plan3).
- Render queue / preview / final mp4 (Plan6).
