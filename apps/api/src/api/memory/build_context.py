"""D2 — Context window builder.

Assembles all memory tiers into an ordered list of ChatMessages, then trims to
stay within `token_cap`.  Trim order: oldest compressed chunks first, then the
working-memory event count; canon and retrieval are never trimmed.
"""

from __future__ import annotations

import hashlib
import json
import logging

from orchestrator.schemas.canon import ProjectCanon
from orchestrator.schemas.dsl import BlenderDsl

from api.memory import canon as canon_mod
from api.memory import compressed as compressed_mod
from api.memory import retrieval as retrieval_mod
from api.memory import working as working_mod

log = logging.getLogger(__name__)

_CHARS_PER_TOKEN = 4  # rough approximation used for trimming


def _token_estimate(msg: dict) -> int:
    return max(1, len(msg.get("content", "")) // _CHARS_PER_TOKEN)


def trim_to_cap(messages: list[dict], token_cap: int) -> list[dict]:
    """Drop messages (oldest compressed first, then trim working) to fit token_cap."""
    total = sum(_token_estimate(m) for m in messages)
    if total <= token_cap:
        return messages

    result = list(messages)
    # Messages are ordered: [canon, retrieval?, compressed…, working, user]
    # Drop from the compressed section (indices between retrieval and working).
    # We identify compressed messages by the "## Compressed History" marker.
    while total > token_cap and len(result) > 2:
        for i, msg in enumerate(result):
            if "Compressed History" in msg.get("content", ""):
                total -= _token_estimate(msg)
                result.pop(i)
                break
        else:
            # No more compressed chunks — trim working events by reducing content.
            for i, msg in enumerate(result):
                if "Recent Events" in msg.get("content", ""):
                    lines = msg["content"].split("\n")
                    # Remove the oldest event line.
                    for j, line in enumerate(lines):
                        if line.startswith("- ["):
                            total -= _CHARS_PER_TOKEN
                            lines.pop(j)
                            result[i] = {**msg, "content": "\n".join(lines)}
                            break
                    else:
                        break  # nothing left to trim
                    break
            else:
                break

    return result


async def build_llm_context(
    project_id: str,
    current_prompt: str,
    project_canon: ProjectCanon,
    scene_graph: BlenderDsl | None = None,
    *,
    token_cap: int = 12_000,
    db_path: str | None = None,
) -> list[dict]:
    """Assemble the full context for an LLM call and trim to *token_cap* tokens."""
    sections: list[dict] = []

    # Tier 1 — canon (always first; must be byte-stable for prompt caching).
    sections.append(canon_mod.build(project_id, project_canon))

    # Tier 5 — retrieval (right after canon so it's in the high-cache prefix).
    retrieval_msg = await retrieval_mod.build(
        project_id, current_prompt, db_path=db_path
    )
    if retrieval_msg:
        sections.append(retrieval_msg)

    # Tier 4 — compressed history chunks.
    compressed_msg = await compressed_mod.build(
        project_id, last_k=3, db_path=db_path
    )
    if compressed_msg:
        sections.append(compressed_msg)

    # Tier 3 — working memory (scene graph + recent events).
    working_msg = await working_mod.build(
        project_id, scene_graph, last_n_events=20, db_path=db_path
    )
    sections.append(working_msg)

    # User turn.
    sections.append({"role": "user", "content": current_prompt})

    trimmed = trim_to_cap(sections, token_cap)

    # Log SHA256 of the assembled context for cache-hit auditing (D6 cold-start check).
    context_bytes = json.dumps(trimmed, sort_keys=True).encode()
    sha = hashlib.sha256(context_bytes).hexdigest()
    log.debug("build_llm_context project=%s sha256=%s tokens≈%d",
              project_id, sha, sum(_token_estimate(m) for m in trimmed))

    return trimmed
