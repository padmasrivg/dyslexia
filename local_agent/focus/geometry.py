"""Pure geometry helpers. No OpenCV, so they are trivially testable."""
from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple

BBox = Tuple[int, int, int, int]


def point_in_bbox(x: float, y: float, bbox: Sequence[int], padding: int = 0) -> bool:
    x1, y1, x2, y2 = bbox
    return (x1 - padding) <= x <= (x2 + padding) and (y1 - padding) <= y <= (y2 + padding)


def bbox_area(bbox: Sequence[int]) -> int:
    return max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1])


def bbox_iou(a: Sequence[int], b: Sequence[int]) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter == 0:
        return 0.0
    union = bbox_area(a) + bbox_area(b) - inter
    return inter / float(union) if union else 0.0


def bbox_center(bbox: Sequence[int]) -> Tuple[float, float]:
    return (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0


def find_focused(
    point: Optional[Tuple[float, float]], boxes: Iterable[Sequence[int]], padding: int = 0
) -> Optional[int]:
    """Index of the box that contains the point; the smallest wins when boxes overlap."""
    if point is None:
        return None
    best, best_area = None, None
    for i, b in enumerate(boxes):
        if point_in_bbox(point[0], point[1], b, padding):
            a = bbox_area(b)
            if best is None or a < best_area:
                best, best_area = i, a
    return best
