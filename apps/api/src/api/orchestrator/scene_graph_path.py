"""JSON-pointer-ish path resolver for scene graph OT operations.

Paths use dot notation with optional bracket indexing:
  scene.camera.position.z
  scene.lights[0].intensity
  scene.camera.focal_mm
"""

import re
from typing import Any

_SEGMENT_RE = re.compile(r'([^.\[]+)(?:\[(\d+)\])?\.?')


def _parse(path: str) -> list[str | int]:
    segments: list[str | int] = []
    for m in _SEGMENT_RE.finditer(path):
        key, idx = m.group(1), m.group(2)
        segments.append(key)
        if idx is not None:
            segments.append(int(idx))
    return segments


def _walk(obj: Any, segments: list[str | int], depth: int) -> Any:
    cur = obj
    for seg in segments[:depth]:
        cur = cur[seg]
    return cur


def get_value(obj: Any, path: str) -> Any:
    segs = _parse(path)
    return _walk(obj, segs, len(segs))


def set_value(obj: Any, path: str, value: Any) -> None:
    segs = _parse(path)
    parent = _walk(obj, segs, len(segs) - 1)
    parent[segs[-1]] = value


def delete_value(obj: Any, path: str) -> None:
    segs = _parse(path)
    parent = _walk(obj, segs, len(segs) - 1)
    last = segs[-1]
    if isinstance(last, int):
        parent.pop(last)
    else:
        del parent[last]


def insert_value(obj: Any, path: str, index: int, value: Any) -> None:
    lst = get_value(obj, path)
    lst.insert(index, value)


def path_touches_lock(op_path: str, locked_path: str) -> bool:
    """True if op_path is equal to, or a sub-path of, locked_path."""
    return (
        op_path == locked_path
        or op_path.startswith(locked_path + ".")
        or op_path.startswith(locked_path + "[")
    )
