# Plan 7 — Memory Hardening + Semantic Retrieval

> Status: **Not started**
> Depends on: Plan1 (LangGraph engine), Plan2 (HTTP surface), Plan3 (UAR), Plan6
> Unblocks: long-horizon project sessions; cost reduction across iterations

## Integration with the LangGraph orchestrator

LangGraph's `SqliteSaver` (introduced in Plan2) already covers **working memory and time-travel** for free — Plan7 no longer needs to invent these. What Plan7 adds is everything *above* the checkpoint store:
- `ProjectCanon` injection into the system message of every `IntentValidator` and `SceneGraphGenerator` call — kept byte-identical for prompt-cache hits.
- **Retrieval node** added between `intent_validator` and the rest of the graph: a pure-Python node that queries `sqlite-vss` for prior rejections + style overrides similar to the current intent and injects them into `AgentState` for the generator's system prompt.
- **Compression task**: an arq cron job that summarizes long checkpoint chains into `CompressedChunk` rows. The chunks are read by the same retrieval node.

The five "tiers" in the original Plan7 map onto:
1. **Canon** — injected into every system message (Plan2 persistence + Plan7 injection helper).
2. **UAR + embeddings** — Plan3 UAR extended with `embedding BLOB`.
3. **Working memory** — `MemorySaver` / `SqliteSaver` checkpoints (free).
4. **Compressed history** — new arq job + SQLite table.
5. **Semantic retrieval** — new LangGraph node + `sqlite-vss` index.

## Goal

Make the system get smarter and cheaper the longer a project runs. Five distinct memory tiers feed deterministically into every LLM call, and a semantic retrieval index ensures the model never re-suggests something the user has already rejected.

## Deliverables

### D1. Hierarchical memory tiers
Each tier is a module in `apps/api/src/memory/` with a single function `build(project_id, ctx) -> MemorySection`. Building the prompt is the concatenation of these sections in a fixed order.

- **`canon.py`** — `ProjectCanon` rendered as a system message. Identical bytes across the lifetime of a project → prompt cache hits.
- **`uar.py`** (extends Plan3) — adds an `embedding BLOB` column to the `assets` table. Embeddings computed once on insert via `text-embedding-3-small` over the prompt + tags. Used by `retrieval.py`.
- **`working.py`** — current `SceneGraph` (compact JSON) + the last N (default 20) DAG events serialized as a short log. Re-computed on each LLM call.
- **`compressed.py`** — every 20 new DAG events, an LLM-summarization task writes a `CompressedChunk` row to SQLite:
  ```python
  class CompressedChunk(BaseModel):
      id: str
      project_id: str
      from_event_id: str
      to_event_id: str
      summary: str           # <= 500 tokens
      embedding: list[float] # for retrieval
  ```
- **`retrieval.py`** — `sqlite-vss`-backed vector index over `RejectedConcept` and `StyleOverride` rows. Query: top-k by cosine similarity to the current intent embedding.

### D2. Context window builder
- `apps/api/src/memory/build_context.py`:
  ```python
  def build_llm_context(project_id, current_intent, token_cap=12_000) -> list[ChatMessage]:
      sections = [
          canon.build(project_id),
          retrieval.build(project_id, query=current_intent),   # top-3 rejections + top-3 style overrides
          compressed.build(project_id, last_k=3),
          working.build(project_id, last_n_events=20),
          {"role": "user", "content": current_intent.raw_prompt},
      ]
      return trim_to_cap(sections, token_cap)
  ```
- Trim policy: drop oldest compressed chunks first, then trim the working-memory event log, never trim canon or retrieval.
- Deterministic ordering ensures the static prefix (canon + tools) is byte-identical across calls → prompt caching pays off.

### D3. Prompt cache leverage
- `apps/api/src/orchestrator/llm_client.py` (from Plan2) refactored so the system message and tool definitions are passed as the cacheable prefix.
- Use OpenAI's `prompt_cache_key` and Anthropic's `cache_control` markers where supported.
- Telemetry: log `cached_tokens` per call to a `llm_usage` SQLite table for cost analysis.

### D4. Rejection capture
- Every `ApprovalResolved` event whose `decision == "reject"` triggers `memory.retrieval.record_rejection(intent, reason)`.
- Stored with the original prompt, the offending intent (or generated asset id), and a free-form reason from the user.
- Future intent generations include the top-3 most similar rejections in the system prompt with a clear directive: *"Avoid the following previously-rejected directions: ..."*.

### D5. Style override capture
- A new event kind `StyleOverridePinned` recorded when the user explicitly pins something they like (e.g. "always use this lighting profile" via a star button in the FE).
- Stored and embedded in `style_overrides`. Surfaced via `retrieval.py` on every intent build.

### D6. Cold-start replay
- Memory tiers must rebuild deterministically from the event log alone — no separate state to migrate.
- On project open, `canon`, `working`, and `retrieval` rebuild in <500ms for projects up to 1000 events.
- `compressed` chunks are persisted (LLM-derived, expensive to recompute) but tagged with the event range so a missing chunk can be rebuilt on demand.

## Critical files to create

```
apps/api/src/memory/__init__.py
apps/api/src/memory/canon.py
apps/api/src/memory/uar.py                   # extends Plan3 UAR with embeddings
apps/api/src/memory/working.py
apps/api/src/memory/compressed.py
apps/api/src/memory/retrieval.py
apps/api/src/memory/build_context.py
apps/api/src/memory/embeddings.py            # OpenAI text-embedding-3-small wrapper w/ cache
apps/api/src/queue/tasks/compress_history.py # arq task scheduled every 20 events
apps/api/src/routes/style.py                 # POST /projects/{id}/style-overrides
apps/api/tests/test_context_builder_caps.py
apps/api/tests/test_retrieval_recall.py
apps/api/tests/test_cold_start_replay.py
apps/web/components/ControlPanel/RejectionReasonPrompt.tsx
apps/web/components/ControlPanel/StylePinButton.tsx
```

Extend:
- `apps/api/src/dag/reducers.py` — `RejectionCaptured`, `StyleOverridePinned`, `HistoryCompressed`.
- `apps/api/src/orchestrator/intent_validator.py` (Plan2) — replace ad-hoc prompt building with `build_llm_context`.

## Dependencies

- `sqlite-vss` (vector search extension for SQLite).
- OpenAI `text-embedding-3-small` (cheap, ~1500 dims).

## Verification

1. **Rejection recall**: in a fresh project, generate three subjects, reject all three with reasons "too saturated", "wrong garment", "wrong pose" → fourth generation's prompt visibly contains "avoid: too saturated, wrong garment, wrong pose" (inspect via logged prompt).
2. **Style pin**: pin a lighting profile from shot 1 → shot 2's intent prompt includes that profile in the style-overrides section.
3. **Token cap**: project with 200 DAG events still produces a context under 12k tokens; oldest compressed chunks are dropped first. Verify via the trim logs.
4. **Cold-start determinism**: with a saved project, restart api, open the project → first LLM call's prompt bytes match the pre-restart bytes byte-for-byte (logged via SHA256 of the assembled context).
5. **Cache hit rate**: across 10 successive intent calls, `cached_tokens / total_input_tokens` ≥ 60% (the canon + tools prefix should always cache).

## Out of scope

- Cross-project retrieval (one project's rejections shouldn't leak into another).
- Fine-tuned embeddings (off-the-shelf is enough for this scale).
- Live editor commands like "remind me never to do X" (could be added — currently rejections are captured implicitly).
