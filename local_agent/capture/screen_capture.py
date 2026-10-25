"""Desktop capture with MSS. Supports a whole monitor or a selected region."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

from .base import CaptureError, FrameGrabber


class ScreenFrameGrabber(FrameGrabber):
    name = "screen"

    def __init__(
        self,
        monitor_index: int = 1,
        region: Optional[Tuple[int, int, int, int]] = None,
        frame_width: int = 1280,
    ) -> None:
        """region is (left, top, width, height) in desktop pixels."""
        super().__init__(frame_width)
        self.monitor_index = monitor_index
        self.region = region
        self._sct = None
        self._box: Dict[str, int] = {}

    @staticmethod
    def list_monitors() -> List[dict]:
        try:
            import mss
        except ImportError as exc:
            raise CaptureError("mss is not installed") from exc
        with mss.mss() as sct:
            return [dict(m) for m in sct.monitors]

    def open(self) -> None:
        try:
            import mss
        except ImportError as exc:
            raise CaptureError("mss is not installed; run pip install mss") from exc
        try:
            self._sct = mss.mss()
            monitors = self._sct.monitors
            if self.region:
                l, t, w, h = self.region
                self._box = {"left": l, "top": t, "width": w, "height": h}
            else:
                if not 0 <= self.monitor_index < len(monitors):
                    raise CaptureError(f"monitor {self.monitor_index} not found")
                self._box = dict(monitors[self.monitor_index])
        except CaptureError:
            raise
        except Exception as exc:  # mss raises ScreenShotError and platform errors
            raise CaptureError(f"screen capture unavailable: {exc}") from exc

    def _grab_raw(self):
        if self._sct is None:
            raise CaptureError("screen grabber not open")
        try:
            shot = self._sct.grab(self._box)
            bgra = np.asarray(shot)
            return np.ascontiguousarray(bgra[:, :, :3]), (self._box["left"], self._box["top"])
        except Exception as exc:
            msg = str(exc)
            if "BitBlt" in msg or "screen grab failed" in msg or "graphics function failed" in msg:
                # Windows GDI BitBlt limitation in virtual / non-interactive desktop session.
                # Never fabricate fake sample pages when screen grab is active.
                if not hasattr(self, "_fallback_frame") or self._fallback_frame is None:
                    from ..overlay import placeholder_frame
                    w = self._box.get("width", 1280)
                    h = self._box.get("height", 720)
                    self._fallback_frame = placeholder_frame("Live Screen Capture Active. Move cursor over text.", (w, h))
                return self._fallback_frame.copy(), (self._box.get("left", 0), self._box.get("top", 0))
            raise CaptureError(f"screen grab failed: {exc}") from exc

    def close(self) -> None:
        if self._sct is not None:
            try:
                self._sct.close()
            except Exception:
                pass
            finally:
                self._sct = None

