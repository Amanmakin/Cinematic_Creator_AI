"""subject_classifier node — routes a prompt to object/landscape/abstract.

Pure LLM structured-output node. Writes `subject_class` and
`subject_class_confidence` to state. Routing logic lives in routing.py;
this node only labels.
"""

from __future__ import annotations

import logging
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from orchestrator import llm as llm_module
from orchestrator.node_logger import llm_call, llm_response, node_step
from orchestrator.state import AgentState

log = logging.getLogger(__name__)


class SubjectClassification(BaseModel):
    subject_class: Literal["object", "landscape", "abstract"]
    confidence: float = Field(ge=0.0, le=1.0)


_KEYWORD_HINTS: dict[str, tuple[str, ...]] = {
    "landscape": (
        "mountain", "forest", "desert", "beach", "river", "lake", "ocean",
        "valley", "canyon", "skyline", "horizon", "field", "meadow", "tundra",
        "jungle", "savanna", "glacier",
    ),
    "abstract": (
        "dread", "joy", "anxiety", "ethereal", "swirling", "dream", "vibe",
        "energy", "aura", "haze", "essence", "feeling", "emotion",
    ),
}


def _heuristic_class(prompt: str) -> tuple[str, float] | None:
    """Cheap keyword pass used as a safety net + cache key for dummy/offline LLMs."""
    low = prompt.lower()
    for label, words in _KEYWORD_HINTS.items():
        if any(w in low for w in words):
            return label, 0.75
    return None


def subject_classifier_node(state: AgentState) -> dict:
    with node_step(
        "subject_classifier",
        prompt=state.user_prompt[:80],
    ) as out:
        system_prompt = llm_module.load_prompt("subject_class_system.md")
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"PROMPT:\n{state.user_prompt}"),
        ]

        result: SubjectClassification
        try:
            llm = llm_module.make_llm()
            llm_call(getattr(llm, "model_name", "?"), len(messages))
            structured = llm.with_structured_output(SubjectClassification, include_raw=True)
            raw = structured.invoke(messages)
            llm_response(raw.get("raw"), raw.get("parsing_error"))
            parsed = raw.get("parsed")
            if parsed is None:
                raise ValueError("LLM returned no parsed SubjectClassification")
            result = parsed  # type: ignore[assignment]
        except Exception as exc:
            log.warning("subject_classifier LLM failed (%s); using keyword heuristic", exc)
            hinted = _heuristic_class(state.user_prompt) or ("object", 0.4)
            result = SubjectClassification(
                subject_class=hinted[0],  # type: ignore[arg-type]
                confidence=hinted[1],
            )

        out.update(
            subject_class=result.subject_class,
            confidence=round(result.confidence, 3),
            status="subject_classified",
        )

        return {
            "subject_class": result.subject_class,
            "subject_class_confidence": float(result.confidence),
            "execution_status": "subject_classified",
        }
