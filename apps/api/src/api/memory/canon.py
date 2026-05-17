"""Tier 1 — ProjectCanon rendered as a stable system-message section.

Byte-identical output across the lifetime of a project enables prompt-cache hits.
"""

from __future__ import annotations

import json

from orchestrator.schemas.canon import ProjectCanon


def build(project_id: str, canon: ProjectCanon) -> dict:
    """Return a system-role ChatMessage containing the serialised project canon.

    The JSON is sorted so the bytes are deterministic regardless of dict insertion order.
    """
    body = json.dumps(canon.model_dump(), sort_keys=True, indent=2)
    content = f"## Project Canon\n\n```json\n{body}\n```"
    return {"role": "system", "content": content}
