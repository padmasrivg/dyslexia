"""Webcam / document camera capture with cv2.VideoCapture."""
from __future__ import annotations

import os
import sys
import time
from typing import Union

# Silence OpenCV internal C++ warnings (especially MSMF error spam on Windows)
os.environ["OPENCV_LOG_LEVEL"] = "OFF"
os.environ["OPENCV_VIDEOIO_PRIORITY_MSMF"] = "0"

import cv2
try:
    cv2.setLogLevel(cv2.LOG_LEVEL_ERROR)
except Exception:
    pass

from .base import CaptureError, FrameGrabber


class CameraFrameGrabber(FrameGrabber):
    name = "camera"

    def __init__(self, camera: Union[int, str] = 0, frame_width: int = 1280, request_size=(1920, 1080), flip_horizontal: bool = False) -> None:
        super().__init__(frame_width)
        self.camera = camera
        self.request_size = request_size
        self.flip_horizontal = flip_horizontal
        self._cap = None

    def toggle_flip(self) -> bool:
        self.flip_horizontal = not self.flip_horizontal
        return self.flip_horizontal

    def open(self) -> None:
        cap = None
        # On Windows, try CAP_DSHOW first to avoid MSMF grabFrame -1072875772 conflicts
        if sys.platform == "win32" and isinstance(self.camera, int):
            try:
                cap = cv2.VideoCapture(self.camera, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    cap.release()
                    cap = None
            except Exception:
                cap = None
        if cap is None:
            cap = cv2.VideoCapture(self.camera)

        if not cap.isOpened():
            cap.release()
            raise CaptureError(f"camera {self.camera!r} could not be opened")
        if self.request_size:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.request_size[0])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.request_size[1])
        self._cap = cap

    def _grab_raw(self):
        if self._cap is None:
            raise CaptureError("camera not open")
        ok, frame = self._cap.read()
        if not ok or frame is None:
            time.sleep(0.05)
            raise CaptureError("camera returned no frame")
        if self.flip_horizontal:
            frame = cv2.flip(frame, 1)
        return frame, (0, 0)

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
