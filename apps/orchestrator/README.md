# orchestrator (Plan1)

LangGraph state machine that turns a user prompt into a strictly typed `BlenderDsl`.

## Setup

```bash
cd apps/orchestrator
uv sync --extra dev
cp ../../.env.example ../../.env   # then put OPENAI_API_KEY=...
```

## Run the demo

```bash
uv run python main.py
```

Prints a final `AgentState` JSON with `execution_status == "completed"` and a
populated `scene_graph` (assuming `OPENAI_API_KEY` is set).

## Tests

```bash
uv run pytest -q
```

All tests mock the LLM seam (`orchestrator.llm.make_llm`) — no network required.

## Layout

```
src/orchestrator/
├── state.py             # AgentState (Pydantic v2)
├── schemas/             # canon / intent / dsl
├── nodes/               # 5 graph nodes
├── routing.py           # conditional-edge functions
├── graph.py             # StateGraph build + compile + MemorySaver
├── llm.py               # ChatOpenAI factory + prompt loader
└── prompts/             # system prompts
```
