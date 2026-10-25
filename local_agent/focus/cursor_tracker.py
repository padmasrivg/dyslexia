"""Focus sources.

`FocusSource` is the seam for future eye-gaze tracking: a gaze estimator only
has to implement `position()` and return frame-space coordinates, and nothing
else in the agent changes.

Implemented sources:
  SystemCursorSource  real OS pointer through pynput, mapped to frame space
  WebPointerSource    pointer position reported by the web UI over the local API
                      (used for camera mode and the demo, where the page being
                      read is shown inside the browser)
  GazeSource          documented stub, raises NotImplementedError
"""
from __future__ import annotations

import abc
import threading
import time
from typing import Optional, Tuple

from ..datatypes import Frame

Point = Tuple[float, float]


class FocusSource(abc.ABC):
    name = "base"

    @abc.abstractmethod
    def position(self, frame: Frame) -> Optional[Point]:
        """Focus point in processed-frame pixels, or None when unknown."""


class SystemCursorSource(FocusSource):
    name = "system-cursor"

    def __init__(self) -> None:
        try:
            from pynput.mouse import Controller

            self._mouse = Controller()
        except Exception as exc:  # no display, missing backend, or no permission
            raise RuntimeError(f"system cursor unavailable: {exc}") from exc

    def position(self, frame: Frame) -> Optional[Point]:
        try:
            gx, gy = self._mouse.position
        except Exception:
            return None
        ox, oy = frame.origin
        x, y = (gx - ox) * frame.scale, (gy - oy) * frame.scale
        h, w = frame.image.shape[:2]
        return (x, y) if 0 <= x < w and 0 <= y < h else None


class WebPointerSource(FocusSource):
    name = "web-pointer"

    def __init__(self, stale_after_s: float = 2.0) -> None:
        self._lock = threading.Lock()
        self._pt: Optional[Point] = None
        self._t = 0.0
        self.stale_after_s = stale_after_s

    def set_normalised(self, nx: Optional[float], ny: Optional[float]) -> None:
        with self._lock:
            if nx is None or ny is None:
                self._pt = None
            else:
                self._pt = (float(nx), float(ny))
                self._t = time.time()

    def position(self, frame: Frame) -> Optional[Point]:
        with self._lock:
            pt, t = self._pt, self._t
        if pt is None or time.time() - t > self.stale_after_s:
            return None
        h, w = frame.image.shape[:2]
        if not (0.0 <= pt[0] <= 1.0 and 0.0 <= pt[1] <= 1.0):
            return None
        return pt[0] * w, pt[1] * h


class GazeSource(FocusSource):
    """Placeholder for eye-gaze tracking. Not implemented in this prototype."""

    name = "gaze (not implemented)"

    def position(self, frame: Frame) -> Optional[Point]:
        raise NotImplementedError("Eye-gaze tracking is future work; use SystemCursorSource or WebPointerSource")
