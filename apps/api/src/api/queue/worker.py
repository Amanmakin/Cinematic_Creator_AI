"""arq worker definitions for three isolated queues.

Run each queue in a separate process:
  arq api.queue.worker.VisualWorkerSettings
  arq api.queue.worker.RenderWorkerSettings
  arq api.queue.worker.ValidateWorkerSettings
"""

from __future__ import annotations

import os

from arq.connections import RedisSettings

from api.queue.tasks.compress_history import compress_history
from api.queue.tasks.render_final import render_final
from api.queue.tasks.render_preview import render_preview
from api.queue.tasks.validate_dsl import validate_dsl
from api.queue.tasks.visual import generate_visual

_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
_redis_settings = RedisSettings.from_dsn(_REDIS_URL)


class VisualWorkerSettings:
    """Handles Replicate / ComfyUI generation calls."""

    functions = [generate_visual]
    redis_settings = _redis_settings
    queue_name = "arq:visual"
    max_jobs = int(os.environ.get("VISUAL_CONCURRENCY", "4"))
    job_timeout = 600


class RenderWorkerSettings:
    """Handles Blender subprocess renders — single concurrency (Blender is heavy)."""

    functions = [render_preview, render_final]
    redis_settings = _redis_settings
    queue_name = "arq:render"
    max_jobs = 1
    job_timeout = 1800


class ValidateWorkerSettings:
    """Handles physical validation + DSL compile."""

    functions = [validate_dsl]
    redis_settings = _redis_settings
    queue_name = "arq:validate"
    max_jobs = int(os.environ.get("VALIDATE_CONCURRENCY", "8"))
    job_timeout = 60


class CompressWorkerSettings:
    """Handles history compression (LLM summarisation of event batches)."""

    functions = [compress_history]
    redis_settings = _redis_settings
    queue_name = "arq:compress"
    max_jobs = 2
    job_timeout = 120
