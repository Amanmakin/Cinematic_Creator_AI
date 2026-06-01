uv run uvicorn api.main:app --reload \
  --reload-dir src \
  --reload-dir ../orchestrator/src \
  --port 8000
