"""Probe headless Blender for version, engines, GPU, and add-on availability.

Result is cached at apps/api/state/capabilities.json and refreshed on API startup.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any

_PROBE_SCRIPT = textwrap.dedent("""
import json, sys
import bpy

result = {
    "blender_version": list(bpy.app.version),
    "blender_version_string": bpy.app.version_string,
    "engines": list(bpy.types.RenderEngine.__subclasses__()),
    "gpu_available": False,
    "gltf_addon": False,
}

# Check for GPU
try:
    import _cycles
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.refresh_devices()
    gpus = [d for d in prefs.devices if d.type != "CPU"]
    result["gpu_available"] = len(gpus) > 0
except Exception:
    pass

# Check engine names more reliably
engine_ids = [e.bl_idname for e in bpy.types.RenderEngine.__subclasses__()]
result["engines"] = engine_ids
result["eevee_available"] = "BLENDER_EEVEE" in engine_ids or "BLENDER_EEVEE_NEXT" in engine_ids
result["cycles_available"] = "CYCLES" in engine_ids

# Check glTF IO add-on
try:
    import io_scene_gltf2  # noqa: F401
    result["gltf_addon"] = True
except ImportError:
    result["gltf_addon"] = "io_scene_gltf2" in bpy.context.preferences.addons

print(json.dumps(result))
""")


def probe_blender(blender_bin: str = "blender") -> dict[str, Any]:
    """Run a bpy probe and return capability dict.

    Raises RuntimeError if Blender cannot be found or fails to run.
    """
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(_PROBE_SCRIPT)
        probe_path = f.name

    try:
        result = subprocess.run(
            [blender_bin, "--background", "--python", probe_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        raise RuntimeError(f"Blender binary not found: {blender_bin}")
    finally:
        Path(probe_path).unlink(missing_ok=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"Blender probe failed (exit {result.returncode}):\n{result.stderr[-500:]}"
        )

    # Find the JSON line in stdout (Blender may emit other lines before it)
    for line in reversed(result.stdout.splitlines()):
        stripped = line.strip()
        if stripped.startswith("{"):
            return json.loads(stripped)

    raise RuntimeError(f"No JSON output from Blender probe:\n{result.stdout[-500:]}")


_CAPABILITIES_PATH = (
    Path(__file__).parent.parent.parent  # workers/ → project root
    / "apps" / "api" / "state" / "capabilities.json"
)


def load_cached_capabilities() -> dict[str, Any] | None:
    if _CAPABILITIES_PATH.exists():
        try:
            return json.loads(_CAPABILITIES_PATH.read_text())
        except Exception:
            return None
    return None


def refresh_capabilities(blender_bin: str = "blender") -> dict[str, Any]:
    """Re-probe Blender and write the result to the cache file."""
    caps = probe_blender(blender_bin)
    _CAPABILITIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CAPABILITIES_PATH.write_text(json.dumps(caps, indent=2))
    return caps


def get_capabilities(blender_bin: str = "blender") -> dict[str, Any]:
    """Return cached capabilities if available, otherwise probe Blender."""
    cached = load_cached_capabilities()
    if cached is not None:
        return cached
    return refresh_capabilities(blender_bin)


def assert_eevee_available(caps: dict[str, Any]) -> None:
    """Raise RuntimeError if EEVEE is not reported as available."""
    if not caps.get("eevee_available", False):
        raise RuntimeError(
            "EEVEE render engine is not available in the detected Blender installation. "
            f"Available engines: {caps.get('engines', [])}"
        )


def assert_gltf_available(caps: dict[str, Any]) -> None:
    """Raise RuntimeError if glTF IO add-on is missing."""
    if not caps.get("gltf_addon", False):
        raise RuntimeError(
            "Blender glTF IO add-on (io_scene_gltf2) is not available. "
            "Ensure Blender 2.80+ is installed."
        )


if __name__ == "__main__":
    blender = sys.argv[1] if len(sys.argv) > 1 else "blender"
    try:
        caps = refresh_capabilities(blender)
        print(json.dumps(caps, indent=2))
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
