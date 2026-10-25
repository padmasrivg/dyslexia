"""Abstract frame grabber plus the shared resize step."""
from __future__ import annotations

import abc
import time
from typing import Optional, Tuple

import cv2
import numpy as np

from ..datatypes import Frame


class CaptureError(RuntimeError):
    """Raised when a source cannot be opened or read."""


def normalise_width(image: np.ndarray, target_width: int) -> Tuple[np.ndarray, float]:
    """Resize to a fixed width so every downstream threshold is resolution independent."""
    h, w = image.shape[:2]
    if w == 0 or target_width <= 0:
        raise CaptureError("empty frame")
    scale = target_width / float(w)
    if abs(scale - 1.0) < 1e-3:
        return image, 1.0
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    return cv2.resize(image, (target_width, max(1, int(round(h * scale)))), interpolation=interp), scale


class FrameGrabber(abc.ABC):
    name = "base"

    def __init__(self, frame_width: int = 1280) -> None:
        self.frame_width = frame_width

    @abc.abstractmethod
    def open(self) -> None: ...

    @abc.abstractmethod
    def _grab_raw(self) -> Tuple[np.ndarray, Tuple[int, int]]:
        """Return (BGR image, source-space origin of the capture region)."""

    @abc.abstractmethod
    def close(self) -> None: ...

    def grab(self) -> Frame:
        raw, origin = self._grab_raw()
        img, scale = normalise_width(raw, self.frame_width)
        return Frame(image=img, scale=scale, origin=origin, source=self.name, captured_at=time.time())

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()
