"""Orchestrator-side thin wrapper that spawns headless Blender to render a scene."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class RenderProgress:
    kind: str = "RenderProgress"
    message: str = ""
    frame: int | None = None


@dataclass
class RenderCompleted:
    kind: str = "RenderCompleted"
    output_dir: str = ""
    frame_path: str = ""


@dataclass
class RenderTimedOut:
    kind: str = "RenderTimedOut"
    timeout_s: float = 0.0


@dataclass
class RenderFailed:
    kind: str = "RenderFailed"
    returncode: int = 0
    stderr_tail: str = ""


RenderEvent = RenderProgress | RenderCompleted | RenderTimedOut | RenderFailed

_SCRIPT = Path(__file__).with_name("render.py")


def run_render(
    glb_path: str,
    extras_path: str,
    out_dir: str,
    *,
    blender_bin: str = "blender",
    timeout_s: float = 300.0,
    on_event: Callable[[RenderEvent], None] | None = None,
) -> RenderEvent:
    """Spawn blender --background and render one frame.

    Emits RenderProgress events to *on_event* as stdout lines arrive.
    Returns the terminal RenderCompleted / RenderTimedOut / RenderFailed event.
    """
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    cmd = [
        blender_bin,
        "--background",
        "--python", str(_SCRIPT),
        "--",
        glb_path,
        extras_path,
        out_dir,
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=os.setsid,
        )
    except FileNotFoundError:
        ev = RenderFailed(returncode=-1, stderr_tail=f"blender binary not found: {blender_bin}")
        if on_event:
            on_event(ev)
        return ev

    stderr_lines: list[str] = []

    def _read_stderr() -> None:
        for line in proc.stderr:  # type: ignore[union-attr]
            stderr_lines.append(line.rstrip())

    stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
    stderr_thread.start()

    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            stripped = line.rstrip()
            ev = RenderProgress(message=stripped)
            if on_event:
                on_event(ev)
            if stripped.startswith("CVC_FRAME:"):
                parts = stripped.split(":", 2)
                if len(parts) == 3:
                    try:
                        ev.frame = int(parts[1])
                    except ValueError:
                        pass

        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            _kill_process_group(proc)
            ev_timeout = RenderTimedOut(timeout_s=timeout_s)
            if on_event:
                on_event(ev_timeout)
            return ev_timeout

    except Exception:
        _kill_process_group(proc)
        raise

    stderr_thread.join(timeout=5)

    if proc.returncode != 0:
        tail = "\n".join(stderr_lines[-20:])
        ev_fail = RenderFailed(returncode=proc.returncode, stderr_tail=tail)
        if on_event:
            on_event(ev_fail)
        return ev_fail

    frame_path = str(Path(out_dir) / "frame_0000.png")
    ev_done = RenderCompleted(output_dir=out_dir, frame_path=frame_path)
    if on_event:
        on_event(ev_done)
    return ev_done


def _kill_process_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
