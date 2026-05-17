"""Single seam for LLM construction so tests can monkeypatch one place."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from langchain_openai import ChatOpenAI

DEFAULT_MODEL = os.getenv("ORCHESTRATOR_LLM_MODEL", "gpt-4o-mini")


def make_llm(model: str = DEFAULT_MODEL, temperature: float = 0.2) -> ChatOpenAI:
    return ChatOpenAI(model=model, temperature=temperature, timeout=60)


@lru_cache(maxsize=8)
def load_prompt(name: str) -> str:
    """Read a system prompt file shipped alongside the package."""
    path = Path(__file__).parent / "prompts" / name
    return path.read_text(encoding="utf-8")
