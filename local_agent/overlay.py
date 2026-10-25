"""Visual assistance drawn directly onto the frame with OpenCV.

The highlight uses cv2.rectangle, as in the product brief. Colours are BGR.
Nothing here depends on the web UI: the same annotated frame is what the
MJPEG stream carries and what a local preview window would show.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

from .datatypes import WordBox

INK = (44, 33, 28)            # dark slate, text on light panels
PAPER = (236, 241, 244)       # off white, never pure white
TEAL = (99, 92, 15)           # active focus
AMBER = (0, 120, 214)         # assistance highlight
SLATE = (150, 140, 120)       # idle word boxes
BRICK = (34, 43, 161)         # low confidence / error

FONT = cv2.FONT_HERSHEY_DUPLEX


def wrap_text(text: str, max_chars: int) -> List[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def _badge(img: np.ndarray, text: str, org: Tuple[int, int], fg, bg) -> None:
    (tw, th), base = cv2.getTextSize(text, FONT, 0.55, 1)
    x, y = org
    cv2.rectangle(img, (x, y), (x + tw + 16, y + th + base + 10), bg, -1)
    cv2.putText(img, text, (x + 8, y + th + 5), FONT, 0.55, fg, 1, cv2.LINE_AA)


def draw_explanation(
    img: np.ndarray, bbox: Sequence[int], text: str, source_note: Optional[str] = None
) -> Tuple[int, int, int, int]:
    """Draw a high contrast explanation panel next to bbox. Returns the panel box."""
    H, W = img.shape[:2]
    scale, thick, pad = 0.8, 1, 14
    max_chars = 44
    lines = wrap_text(text, max_chars)
    if source_note:
        lines = lines + [source_note]
    sizes = [cv2.getTextSize(l, FONT, scale, thick)[0] for l in lines]
    line_h = max(s[1] for s in sizes) + 12
    pw = min(W - 20, max(s[0] for s in sizes) + 2 * pad)
    ph = line_h * len(lines) + 2 * pad - 4
    x1, y1, x2, y2 = bbox
    px = int(min(max(10, x1), W - pw - 10))
    below = y2 + 14
    py = below if below + ph < H - 10 else max(10, y1 - 14 - ph)
    cv2.rectangle(img, (px, py), (px + pw, py + ph), INK, -1)
    cv2.rectangle(img, (px, py), (px + pw, py + ph), AMBER, 2)
    y = py + pad + line_h - 12
    for i, l in enumerate(lines):
        is_note = source_note is not None and i == len(lines) - 1
        cv2.putText(
            img, l, (px + pad, y), FONT, scale * (0.7 if is_note else 1.0),
            (80, 190, 255) if is_note else PAPER, thick, cv2.LINE_AA,
        )
        y += line_h
    return px, py, px + pw, py + ph


def render_frame(
    frame: np.ndarray,
    words: Sequence[WordBox],
    min_conf: float,
    focus_bbox: Optional[Sequence[int]] = None,
    focus_progress: float = 0.0,
    assistance: Optional[dict] = None,
    simulation: bool = False,
    focus_point: Optional[Tuple[float, float]] = None,
) -> np.ndarray:
    out = frame.copy()
    for w in words:
        colour = SLATE if w.confidence >= min_conf else BRICK
        cv2.rectangle(out, (w.bbox[0], w.bbox[1]), (w.bbox[2], w.bbox[3]), colour, 1)

    if focus_bbox is not None and not assistance:
        x1, y1, x2, y2 = focus_bbox
        cv2.rectangle(out, (x1 - 2, y1 - 2), (x2 + 2, y2 + 2), TEAL, 3)
        bar_w = x2 - x1 + 4
        cv2.rectangle(out, (x1 - 2, y2 + 5), (x1 - 2 + bar_w, y2 + 11), SLATE, 1)
        cv2.rectangle(out, (x1 - 2, y2 + 5), (x1 - 2 + int(bar_w * min(1.0, focus_progress)), y2 + 11), TEAL, -1)

    if assistance:
        x1, y1, x2, y2 = assistance["bbox"]
        cv2.rectangle(out, (x1 - 4, y1 - 4), (x2 + 4, y2 + 4), AMBER, 4)
        note = "MOCK TEXT, not from AWS" if assistance.get("source") == "local-mock" else None
        draw_explanation(out, assistance["bbox"], assistance["definition"], note)

    if focus_point is not None:
        cv2.circle(out, (int(focus_point[0]), int(focus_point[1])), 6, TEAL, 2, cv2.LINE_AA)

    if simulation:
        _badge(out, "SIMULATION: prepared page, real detection and OCR", (10, 10), PAPER, INK)
    return out


def placeholder_frame(message: str, size: Tuple[int, int] = (1280, 720)) -> np.ndarray:
    w, h = size
    img = np.full((h, w, 3), (58, 50, 44), np.uint8)
    (tw, th), _ = cv2.getTextSize(message, FONT, 1.0, 1)
    cv2.putText(img, message, ((w - tw) // 2, h // 2), FONT, 1.0, PAPER, 1, cv2.LINE_AA)
    return img
