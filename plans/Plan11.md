# Plan 11 — Reference-Object Isolation + Image-Only Generation

> Status: **Implemented** (T1–T5 — 2026-06-02; `reference_vision` helper + adapter crop + image-only/auto-caption route + frontend relaxation + docs/tests)
> Depends on: Plan10 (text→3D: TripoSR/Shap-E adapters, `mesh_generator`, `mesh_dispatcher`), Plan8 (hybrid-adapter pattern, local Docker discipline)
> Unblocks: subject-accurate meshes from real photos (reconstruct the *product*, not the hand holding it); prompt-free "drop an image and Generate" flow
> Source: AI Studio feedback — a reference photo of a hand holding a water bottle produced a "hand + blob" wireframe instead of the bottle

## Goal

Two linked capabilities, both served by a single OpenAI-vision **"analyze the reference"** step:

1. **Pick the object first.** Before reconstruction, detect the single main product in the
   reference photo, **crop to its bounding box**, and reconstruct only that — so the mesh is the
   bottle, not the hand + arm + background blob.
2. **Image-only submission.** Allow Generate with a reference image and **no text prompt**, by
   **auto-captioning** the image into a short subject that seeds the existing pipeline.

## Why this is the right shape

The current image→3D path sends raw reference bytes straight to TripoSR
([text_to_3d_adapter.py:92-94](../apps/api/src/api/adapters/text_to_3d_adapter.py#L92-L94)), whose
only preprocessing is `rembg.remove()`
([docker/triposr/app.py:122-130](../docker/triposr/app.py#L122-L130)). `rembg` removes the
*background* but keeps the whole connected *foreground* (hand + arm + bottle). There is no step
that *selects* the product, so TripoSR faithfully reconstructs the whole mass.

A vision model already in reach (`gpt-4o-mini` is the default graph LLM; the OpenAI key is wired
into the mesh adapter) can return both a **bounding box** (→ crop) and a **label** (→ prompt when
none is given). One step, cached per image, solves both requests with no new service, no new graph
node, and no new `AgentState` field — the caption is resolved at the route boundary so graph
topology is unchanged. Offline (`local_only`, no key) degrades gracefully to today's behavior.

## Dependency DAG

```
T1  reference_vision.py helper (analyze + crop)        ─┐  (foundation)
                                                         │
T2  crop wired into text_to_3d_adapter   (← T1)         ─┤  Request 1
T3  optional-prompt + auto-caption in runs.py (← T1)    ─┤  Request 2 (backend)
T4  frontend submit/button relaxation     (parallel)    ─┤  Request 2 (frontend)
                                                         │
T5  docs sync + tests                     (← T1..T4)    ─┘
```

T1 is the only hard prerequisite; T2/T3 depend on it, T4 is independent, T5 closes out.

## T1 — `reference_vision.py` helper (foundation)

- New: `apps/api/src/api/reference_vision.py`. Uses the existing `openai` dependency (see
  [text_to_3d_adapter.py:156-190](../apps/api/src/api/adapters/text_to_3d_adapter.py#L156-L190)) and PIL.
- `analyze_reference_image(image_bytes, api_key, *, hint=None) -> ReferenceAnalysis`
  - Vision model (`gpt-4o`, env override `REFERENCE_VISION_MODEL`) with structured output:
    "Identify the single main product/object a user would want a 3D model of. **Exclude hands,
    arms, people, and background.** Return a short `label` and a normalized bbox `[x0,y0,x1,y1]`
    in 0–1." `hint` (user prompt, if any) biases the selection.
  - Returns `ReferenceAnalysis(label: str | None, bbox_norm: tuple[float,...] | None)`.
  - `@lru_cache` on `sha256(image_bytes)` → one network call per image even when called from both
    the route and the adapter.
  - Graceful fallback: empty/missing key or any OpenAI error → `ReferenceAnalysis(None, None)`.
- `crop_to_object(image_bytes, bbox_norm) -> bytes` — PIL crop with ~8–12% padding, re-encode PNG;
  returns input unchanged when `bbox_norm is None`.
- Verification: unit tests with a mocked OpenAI client (label+bbox parsed; nulls on empty key /
  raised error); `crop_to_object` crops to the padded box and round-trips valid PNG; passthrough
  when bbox is `None`.

## T2 — Crop to the object before TripoSR (Request 1)

- Modify `TextTo3DAdapter._triposr_from_image()`
  ([text_to_3d_adapter.py:137-139](../apps/api/src/api/adapters/text_to_3d_adapter.py#L137-L139)):
  before `self._triposr.generate(...)`, run
  `analysis = analyze_reference_image(image_bytes, self._openai_api_key, hint=subject)` then
  `image_bytes = crop_to_object(image_bytes, analysis.bbox_norm)`. TripoSR's existing `rembg`
  cleans residual background inside the crop. **No change to the TripoSR Docker service.**
- `local_only` has no key → analysis returns nulls → no crop (today's behavior preserved).
- Verification: `_triposr_from_image` sends *cropped* bytes to a mocked `TripoSRClient` (assert the
  bytes differ from input when a bbox is returned; identical when none).

## T3 — Optional prompt + auto-caption (Request 2, backend)

- Modify `apps/api/src/api/routes/runs.py`:
  - `RunRequest.user_prompt: str` → `user_prompt: str = ""` (line 18).
  - In `start_run`, when `body.user_prompt.strip()` is empty:
    - both prompt and `sample_image_urls` empty → `HTTPException(400, "Provide a prompt or a reference image")`.
    - else load the first reference image bytes (reuse `_load_reference_image` from
      [mesh_dispatch.py:35-47](../apps/api/src/api/orchestrator/mesh_dispatch.py#L35-L47)) and set
      `effective_prompt = analyze_reference_image(bytes, settings.openai_api_key).label`, falling
      back to `"the main object from the reference image"` when the label is `None`. (Cached → the
      adapter's later crop reuses the same analysis.)
  - Build `AgentState(user_prompt=effective_prompt, ...)`. The existing pipeline runs unchanged:
    `subject_classifier` → `object` → `route_after_mesh_dispatch` → `mesh_generator` → TripoSR with
    the cropped reference.
- Verification: `POST /projects/{id}/runs` with empty `user_prompt` + `sample_image_urls` → 200 and
  the run is seeded with the caption; both empty → 400.

## T4 — Frontend submit/button relaxation (Request 2, frontend)

- Modify `apps/web/components/ControlPanel/PromptComposer.tsx`:
  - Submit guard (line 40): `if ((!prompt.trim() && previews.length === 0) || !projectId) return;`
  - Button disabled (line 159): `disabled={busy || !projectId || (!prompt.trim() && previews.length === 0)}`
  - Keep passing `prompt.trim()` (now possibly `""`) to `submitPrompt`. Verify `submitPrompt`
    ([projectStore.ts](../apps/web/state/projectStore.ts)) and `submitRun`
    ([lib/api.ts](../apps/web/lib/api.ts)) don't independently reject an empty prompt; relax if so.
  - UX copy: signal that a prompt **or** an image is sufficient.
- Verification: in the running app, Generate is enabled with only an image; with neither it stays
  disabled.

## T5 — Docs + tests

- Update [docs/ARCHITECTURE_SNAPSHOT.md](../docs/ARCHITECTURE_SNAPSHOT.md): new `reference_vision`
  module, the object-crop step in the text→3D adapter, the image-only/auto-caption behavior in the
  runs route; set `Last synced:` to today. (No new node/state field — topology unchanged.)
- Run `apps/api` + `apps/orchestrator` suites for regressions.
- End-to-end (manual): start API + web + TripoSR; upload the water-bottle photo with **no prompt**,
  Generate, confirm the wireframe is **just the bottle** and a caption was used. Repeat with a
  prompt to confirm it biases the pick. Offline check: `MESH_PIPELINE_STRATEGY=local_only` + no key
  still produces a mesh (no crash).
