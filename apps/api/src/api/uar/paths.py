"""Content-addressed blob layout for UAR assets.

Layout: {uar_root}/projects/{project_id}/assets/{sha256[:2]}/{sha256}.{ext}
"""

from __future__ import annotations

import os


def asset_dir(uar_root: str, project_id: str, sha256: str) -> str:
    return os.path.join(uar_root, "projects", project_id, "assets", sha256[:2])


def rgba_path(uar_root: str, project_id: str, sha256: str) -> str:
    d = asset_dir(uar_root, project_id, sha256)
    return os.path.join(d, f"{sha256}_rgba.png")


def alpha_mask_path(uar_root: str, project_id: str, sha256: str) -> str:
    d = asset_dir(uar_root, project_id, sha256)
    return os.path.join(d, f"{sha256}_alpha.png")


def depth_map_path(uar_root: str, project_id: str, sha256: str) -> str:
    d = asset_dir(uar_root, project_id, sha256)
    return os.path.join(d, f"{sha256}_depth.png")


def ensure_asset_dir(uar_root: str, project_id: str, sha256: str) -> str:
    d = asset_dir(uar_root, project_id, sha256)
    os.makedirs(d, exist_ok=True)
    return d
