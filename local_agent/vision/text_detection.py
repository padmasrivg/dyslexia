"""Text detection: where is text on the frame? Independent from OCR.

Two interchangeable detectors share one interface:

* DBNetDetector  uses cv2.dnn.TextDetectionModel_DB with an ONNX model placed in
                 models/ (see models/README.md). This is the primary detector.
* ClassicalDetector  a morphology based detector built only from OpenCV
                 primitives. It is the fallback when no ONNX model is present,
                 and it is labelled as such everywhere it is reported.

`create_detector()` picks DBNet when the model file exists and says which one it chose.
"""
from __future__ import annotations

import abc
import os
from typing import List, Optional, Tuple

import cv2
import numpy as np

from ..datatypes import TextRegion


class TextDetector(abc.ABC):
    name = "base"

    @abc.abstractmethod
    def detect(self, preprocessed: dict) -> List[TextRegion]: ...


def _clip_box(x1: int, y1: int, x2: int, y2: int, w: int, h: int) -> Tuple[int, int, int, int]:
    return max(0, x1), max(0, y1), min(w - 1, x2), min(h - 1, y2)


def merge_overlapping(regions: List[TextRegion], iou_thresh: float = 0.3) -> List[TextRegion]:
    """Greedy merge of heavily overlapping boxes (union box, max confidence)."""
    regions = sorted(regions, key=lambda r: r.bbox[1])
    merged: List[TextRegion] = []
    for r in regions:
        placed = False
        for i, m in enumerate(merged):
            if iou(r.bbox, m.bbox) > iou_thresh:
                b = (
                    min(r.bbox[0], m.bbox[0]),
                    min(r.bbox[1], m.bbox[1]),
                    max(r.bbox[2], m.bbox[2]),
                    max(r.bbox[3], m.bbox[3]),
                )
                merged[i] = TextRegion(b, max(r.confidence, m.confidence))
                placed = True
                break
        if not placed:
            merged.append(r)
    return merged


def iou(a, b) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter == 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / float(area_a + area_b - inter)


class DBNetDetector(TextDetector):
    name = "dbnet-onnx"

    def __init__(self, model_path: str, input_size: Tuple[int, int] = (736, 736),
                 binary_threshold: float = 0.3, polygon_threshold: float = 0.5,
                 max_candidates: int = 400, unclip_ratio: float = 2.0) -> None:
        if not os.path.isfile(model_path):
            raise FileNotFoundError(model_path)
        self.model = cv2.dnn.TextDetectionModel_DB(model_path)
        self.model.setBinaryThreshold(binary_threshold)
        self.model.setPolygonThreshold(polygon_threshold)
        self.model.setMaxCandidates(max_candidates)
        self.model.setUnclipRatio(unclip_ratio)
        # ImageNet style normalisation used by the common DB_TD500 / DB_IC15 exports
        self.model.setInputParams(1.0 / 255.0, input_size, (122.67891434, 116.66876762, 104.00698793), True)
        self.input_size = input_size

    def detect(self, preprocessed: dict) -> List[TextRegion]:
        bgr = preprocessed["bgr"]
        h, w = bgr.shape[:2]
        boxes, confs = self.model.detect(bgr)
        out: List[TextRegion] = []
        for quad, conf in zip(boxes, confs):
            pts = np.asarray(quad, dtype=np.float32).reshape(-1, 2)
            x1, y1 = pts.min(axis=0)
            x2, y2 = pts.max(axis=0)
            x1, y1, x2, y2 = _clip_box(int(x1), int(y1), int(x2), int(y2), w, h)
            if x2 - x1 > 4 and y2 - y1 > 4:
                out.append(TextRegion((x1, y1, x2, y2), float(conf)))
        return out


class ClassicalDetector(TextDetector):
    """Line level text regions from gradients and morphology. No learned model."""

    name = "classical-morphology (fallback, no DBNet model loaded)"

    def __init__(self, min_height: int = 10, max_height_ratio: float = 0.2) -> None:
        self.min_height = min_height
        self.max_height_ratio = max_height_ratio

    def detect(self, preprocessed: dict) -> List[TextRegion]:
        gray = preprocessed["gray"]
        h, w = gray.shape[:2]
        grad = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        _, bw = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        # Join letters into words and words into lines, but not lines into blocks
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(15, w // 45), 3))
        joined = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, kernel)
        joined = cv2.dilate(joined, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
        contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        out: List[TextRegion] = []
        for c in contours:
            x, y, bw_, bh = cv2.boundingRect(c)
            if bh < self.min_height or bh > h * self.max_height_ratio or bw_ < 2 * bh:
                continue
            fill = cv2.countNonZero(bw[y:y + bh, x:x + bw_]) / float(bw_ * bh)
            if not 0.04 < fill < 0.8:
                continue
            pad = 3
            x1, y1, x2, y2 = _clip_box(x - pad, y - pad, x + bw_ + pad, y + bh + pad, w, h)
            out.append(TextRegion((x1, y1, x2, y2), float(min(0.95, 0.5 + fill))))
        return out


def create_detector(model_path: str) -> TextDetector:
    if model_path and os.path.isfile(model_path):
        try:
            return DBNetDetector(model_path)
        except Exception:  # corrupt or incompatible ONNX: fall back and say so
            pass
    return ClassicalDetector()


def detect_regions(detector: TextDetector, preprocessed: dict, min_conf: float = 0.3) -> List[TextRegion]:
    regions = [r for r in detector.detect(preprocessed) if r.confidence >= min_conf]
    regions = merge_overlapping(regions)
    return sorted(regions, key=lambda r: (r.bbox[1] // 10, r.bbox[0]))
