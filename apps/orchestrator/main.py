"""Demo runner — drives the LangGraph orchestrator end-to-end on a fixed prompt."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

# Allow `python apps/orchestrator/main.py` from the repo root.
sys.path.insert(0, str(Path(__file__).parent / "src"))

from orchestrator.graph import build_graph  # noqa: E402
from orchestrator.schemas.canon import ProjectCanon  # noqa: E402
from orchestrator.state import AgentState  # noqa: E402


def run() -> None:
    load_dotenv()

    canon = ProjectCanon(
        aspect_ratio="9:16",
        duration_seconds_max=15,
        aesthetic_tags=["modern", "natural", "cinematic"],
        style_guide="Warm tones, soft natural light, minimal background clutter.",
    )
    state = AgentState(
        user_prompt=(
            "A modern, cinematic advertisement for a new kurti collection, "
            "focusing on slow-motion movement and warm tones."
        ),
        project_canon=canon,
    )

    graph = build_graph()
    config = {"configurable": {"thread_id": "demo-1"}}
    final = graph.invoke(state, config=config)

    rendered = AgentState.model_validate(final)
    print(rendered.model_dump_json(indent=2))


if __name__ == "__main__":
    run()
