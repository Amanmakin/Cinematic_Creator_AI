"""Formatted step-by-step logging for all LangGraph nodes."""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from typing import Any

log = logging.getLogger("orchestrator")

_W = 64  # line width


def _hr(char: str = "─") -> str:
    return char * _W


def _box_line(text: str, fill: str = " ") -> str:
    inner = f" {text} "
    pad = _W - 2 - len(inner)
    return f"│{inner}{fill * max(pad, 0)} │"


def node_start(name: str, **kwargs: Any) -> float:
    """Log the start of a node with optional input summary fields."""
    log.warning("\n┌%s┐", _hr("─"))
    log.warning("│  ▶  NODE: %-*s│", _W - 9, name)
    log.warning("├%s┤", _hr("─"))
    for k, v in kwargs.items():
        val = _truncate(v)
        log.warning("│  %-18s %s%-*s│", f"{k}:", val, max(_W - 22 - len(val), 0), "")
    if kwargs:
        log.warning("├%s┤", _hr("─"))
    return time.perf_counter()


def node_end(name: str, t0: float, **kwargs: Any) -> None:
    """Log the result of a node."""
    elapsed = time.perf_counter() - t0
    for k, v in kwargs.items():
        val = _truncate(v)
        log.warning("│  %-18s %s%-*s│", f"{k}:", val, max(_W - 22 - len(val), 0), "")
    log.warning("├%s┤", _hr("─"))
    log.warning("│  ✓  done in %.2fs%-*s│", elapsed, _W - 18, "")
    log.warning("└%s┘\n", _hr("─"))


def llm_call(model: str, n_messages: int) -> None:
    log.warning("│  ↑  LLM call  model=%-s  messages=%d%-*s│",
                model, n_messages, max(_W - 30 - len(model), 0), "")


def llm_response(raw: Any, parsing_error: Any) -> None:
    if parsing_error:
        log.warning("│  ✗  parsing_error: %s%-*s│",
                    _truncate(str(parsing_error)), max(_W - 22 - len(str(parsing_error)), 0), "")
    else:
        content = ""
        if hasattr(raw, "content"):
            content = _truncate(str(raw.content))
        elif raw is not None:
            content = _truncate(str(raw))
        log.warning("│  ↓  LLM ok    content: %s%-*s│",
                    content, max(_W - 26 - len(content), 0), "")

        usage = getattr(raw, "usage_metadata", None)
        if usage:
            tokens = f"in={usage.get('input_tokens','?')} out={usage.get('output_tokens','?')}"
            log.warning("│     tokens: %s%-*s│", tokens, max(_W - 15 - len(tokens), 0), "")


@contextmanager
def node_step(name: str, **input_kwargs: Any):
    """Context manager: logs start/end and any exception."""
    t0 = node_start(name, **input_kwargs)
    try:
        result: dict[str, Any] = {}
        yield result
        node_end(name, t0, **result)
    except Exception as exc:
        log.warning("│  ✗  EXCEPTION: %s%-*s│", str(exc)[:46], max(_W - 18 - len(str(exc)[:46]), 0), "")
        log.warning("└%s┘\n", _hr("─"))
        raise


def _truncate(v: Any, max_len: int = 38) -> str:
    if isinstance(v, (dict, list)):
        s = json.dumps(v, default=str)
    else:
        s = str(v)
    return s if len(s) <= max_len else s[: max_len - 1] + "…"
