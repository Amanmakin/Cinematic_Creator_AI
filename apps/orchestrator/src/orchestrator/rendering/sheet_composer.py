"""Compose a wireframe reference sheet from individual Blender renders.

Produces a single PNG in the style of a professional Blender wireframe
turnaround sheet: orthographic views, perspective, detail close-ups,
model info, notes, and outliner hierarchy.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Layout constants ──────────────────────────────────────────────────────────
SHEET_W   = 2200
SHEET_H   = 1620
MARGIN    = 10
TITLE_H   = 68
ORTHO_H   = 420
MAIN_H    = 490
INFO_H    = SHEET_H - MARGIN * 5 - TITLE_H - ORTHO_H - MAIN_H

# Colours (RGB tuples)
BG        = (22,  22,  24)
PANEL_BG  = (30,  30,  34)
BORDER    = (55,  55,  62)
LBL_CLR   = (160, 160, 170)
TITLE_CLR = (210, 210, 220)
ACCENT    = (64,  153, 255)
DIM       = (100, 100, 108)
INFO_BG   = (26,  26,  30)


def _try_load_font(size: int):
    """Return a PIL ImageFont, falling back to the built-in bitmap font."""
    try:
        from PIL import ImageFont  # type: ignore[import]
        for candidate in [
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]:
            try:
                return ImageFont.truetype(candidate, size)
            except (IOError, OSError):
                continue
        return ImageFont.load_default()
    except Exception:
        return None


def _load_panel(path: str | None, w: int, h: int):
    """Open and resize an image panel; return a dark placeholder on failure."""
    from PIL import Image  # type: ignore[import]
    if path and Path(path).exists():
        try:
            img = Image.open(path).convert("RGB")
            img = img.resize((w, h), Image.LANCZOS)
            return img
        except Exception:
            pass
    placeholder = Image.new("RGB", (w, h), PANEL_BG)
    return placeholder


def _draw_label(draw, text: str, x: int, y: int, font, color=LBL_CLR):
    draw.text((x, y), text, font=font, fill=color)


def _draw_rect(draw, x0, y0, x1, y1, fill=PANEL_BG, outline=BORDER):
    draw.rectangle([x0, y0, x1, y1], fill=fill, outline=outline)


def compose_wireframe_sheet(
    view_paths: dict[str, str | None],
    stats: dict[str, Any],
    subject_label: str,
    output_path: str,
    notes: list[str] | None = None,
) -> str:
    """Compose all rendered views into a single wireframe reference sheet PNG.

    Args:
        view_paths:    Dict with keys front/side/back/top/persp/detail_0-3 → file paths.
        stats:         Dict from stats.json: vertices/edges/faces/triangles/primitive_labels.
        subject_label: Human-readable subject name for the title bar.
        output_path:   Where to write the final sheet PNG.
        notes:         Optional list of note strings for the notes box.

    Returns:
        output_path (confirmed written).
    """
    try:
        from PIL import Image, ImageDraw  # type: ignore[import]
    except ImportError:
        logger.warning("Pillow not available — skipping wireframe sheet composition")
        return output_path

    sheet = Image.new("RGB", (SHEET_W, SHEET_H), BG)
    draw  = ImageDraw.Draw(sheet)

    font_sm  = _try_load_font(13)
    font_md  = _try_load_font(17)
    font_lg  = _try_load_font(22)
    font_xl  = _try_load_font(26)

    # ── Title bar ─────────────────────────────────────────────────────────────
    ty = MARGIN
    _draw_rect(draw, MARGIN, ty, SHEET_W - MARGIN, ty + TITLE_H, fill=(18, 18, 22), outline=BORDER)
    title = f"{subject_label.upper()} – WIREFRAME (BLENDER)"
    _draw_label(draw, title, MARGIN + 18, ty + 10, font_xl, color=TITLE_CLR)
    _draw_label(draw, "All views in Wireframe Shading", MARGIN + 18, ty + 40, font_sm, color=DIM)

    # ── Orthographic row ──────────────────────────────────────────────────────
    ortho_names = [("FRONT", "front"), ("SIDE", "side"), ("BACK", "back"), ("TOP", "top")]
    oy = MARGIN * 2 + TITLE_H
    panel_w = (SHEET_W - MARGIN * 2) // 4

    for col_i, (label, key) in enumerate(ortho_names):
        px = MARGIN + col_i * panel_w
        img = _load_panel(view_paths.get(key), panel_w - 2, ORTHO_H - 22)
        _draw_rect(draw, px, oy, px + panel_w - 2, oy + ORTHO_H, outline=BORDER)
        sheet.paste(img, (px + 1, oy + 21))
        _draw_label(draw, label, px + 8, oy + 4, font_md, color=LBL_CLR)

    # ── Main row: perspective + details ───────────────────────────────────────
    my       = oy + ORTHO_H + MARGIN
    persp_w  = int((SHEET_W - MARGIN * 2) * 0.60)
    detail_w = SHEET_W - MARGIN * 2 - persp_w - MARGIN

    # Perspective
    _draw_rect(draw, MARGIN, my, MARGIN + persp_w, my + MAIN_H, outline=BORDER)
    persp_img = _load_panel(view_paths.get("persp"), persp_w - 2, MAIN_H - 22)
    sheet.paste(persp_img, (MARGIN + 1, my + 21))
    _draw_label(draw, "PERSPECTIVE", MARGIN + 8, my + 4, font_md, color=LBL_CLR)

    # Details panel
    dx      = MARGIN + persp_w + MARGIN
    detail_labels = ["Backrest Joinery", "Seat & Leg Joinery", "Leg & Stretcher", "Top View (Seat)"]
    det_panel_w = detail_w // 2
    det_panel_h = (MAIN_H - 26) // 2

    _draw_rect(draw, dx, my, dx + detail_w, my + MAIN_H, outline=BORDER)
    _draw_label(draw, "DETAILS (CLOSE-UPS)", dx + 8, my + 4, font_md, color=LBL_CLR)

    for di in range(4):
        row, col_d = divmod(di, 2)
        dpx = dx + col_d * det_panel_w
        dpy = my + 22 + row * det_panel_h
        dimg = _load_panel(view_paths.get(f"detail_{di}"), det_panel_w - 2, det_panel_h - 18)
        _draw_rect(draw, dpx, dpy, dpx + det_panel_w - 1, dpy + det_panel_h - 1, fill=PANEL_BG, outline=BORDER)
        sheet.paste(dimg, (dpx + 1, dpy + 17))
        _draw_label(draw, detail_labels[di], dpx + 6, dpy + 2, font_sm, color=DIM)

    # ── Info row ──────────────────────────────────────────────────────────────
    iy         = my + MAIN_H + MARGIN
    info_total = SHEET_W - MARGIN * 2
    info_col_w = info_total // 3

    # MODEL INFO
    mx0 = MARGIN
    _draw_rect(draw, mx0, iy, mx0 + info_col_w, iy + INFO_H, fill=INFO_BG, outline=BORDER)
    _draw_label(draw, "MODEL INFO", mx0 + 10, iy + 8, font_md, color=ACCENT)
    verts = stats.get("vertices", "—")
    edges = stats.get("edges", "—")
    faces = stats.get("faces", "—")
    tris  = stats.get("triangles", "—")
    info_lines = [
        f"• Vertices:  {verts:,}" if isinstance(verts, int) else f"• Vertices:  {verts}",
        f"• Edges:     {edges:,}" if isinstance(edges, int) else f"• Edges:     {edges}",
        f"• Faces:     {faces:,}" if isinstance(faces, int) else f"• Faces:     {faces}",
        f"• Triangles: {tris:,}"  if isinstance(tris, int)  else f"• Triangles: {tris}",
        "",
        "• Unit System: Metric",
        "• Scale: Real World",
        "• Renderer: Workbench",
    ]
    for li, line in enumerate(info_lines):
        _draw_label(draw, line, mx0 + 10, iy + 34 + li * 17, font_sm, color=LBL_CLR)

    # NOTES
    nx0 = mx0 + info_col_w + MARGIN
    _draw_rect(draw, nx0, iy, nx0 + info_col_w, iy + INFO_H, fill=INFO_BG, outline=BORDER)
    _draw_label(draw, "NOTES", nx0 + 10, iy + 8, font_md, color=ACCENT)
    default_notes = [
        "• Primitives-based wireframe geometry",
        "• LLM-decomposed into metric boxes/cylinders",
        "• Wireframe modifier — outline + ghost fill",
        "• Renders via headless Blender Workbench",
    ]
    note_lines = notes if notes else default_notes
    for li, note in enumerate(note_lines[:8]):
        _draw_label(draw, note, nx0 + 10, iy + 34 + li * 17, font_sm, color=LBL_CLR)

    # OUTLINER
    ox0 = nx0 + info_col_w + MARGIN
    _draw_rect(draw, ox0, iy, SHEET_W - MARGIN, iy + INFO_H, fill=INFO_BG, outline=BORDER)
    _draw_label(draw, "OUTLINER", ox0 + 10, iy + 8, font_md, color=ACCENT)
    labels = stats.get("primitive_labels", [])
    subject_name = subject_label.replace(" ", "_").title()
    _draw_label(draw, f"▿ {subject_name}", ox0 + 10, iy + 34, font_sm, color=LBL_CLR)
    for li, lbl in enumerate(labels[:12]):
        icon = "▸"
        _draw_label(draw, f"  {icon} {lbl}", ox0 + 10, iy + 52 + li * 16, font_sm, color=DIM)

    # ── Save ──────────────────────────────────────────────────────────────────
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, "PNG")
    logger.info("Wireframe sheet saved: %s", output_path)
    return output_path
