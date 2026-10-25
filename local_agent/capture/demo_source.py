"""Prepared reading sample for the competition demo and for headless testing.

This is a SIMULATED input: the page is rendered by OpenCV from the text below.
Detection and OCR still run for real on the rendered pixels. The UI labels this
source as SIMULATION so it is never confused with live screen or camera input.
"""
from __future__ import annotations

from typing import Tuple

import cv2
import numpy as np

from .base import FrameGrabber

SAMPLE_TITLE = "Plants and Light"
SAMPLE_LINES = [
    "Photosynthesis is the process by which green plants make food.",
    "Leaves absorb sunlight and take in carbon dioxide from the air.",
    "Chlorophyll gives leaves their green colour and captures energy.",
    "The plant turns this energy into sugar that helps it grow.",
]


def render_sample_page(width: int = 1280, height: int = 720) -> np.ndarray:
    page = np.full((height, width, 3), (236, 241, 244), np.uint8)  # warm paper, not pure white
    ink = (36, 30, 27)
    cv2.putText(page, SAMPLE_TITLE, (90, 140), cv2.FONT_HERSHEY_DUPLEX, 1.7, ink, 2, cv2.LINE_AA)
    y = 260
    for line in SAMPLE_LINES:
        cv2.putText(page, line, (90, y), cv2.FONT_HERSHEY_DUPLEX, 0.98, ink, 1, cv2.LINE_AA)
        y += 92
    return page


class DemoFrameGrabber(FrameGrabber):
    name = "demo"

    def __init__(self, frame_width: int = 1280) -> None:
        super().__init__(frame_width)
        self._page = render_sample_page()

    def open(self) -> None:
        return None

    def _grab_raw(self) -> Tuple[np.ndarray, Tuple[int, int]]:
        return self._page.copy(), (0, 0)

    def close(self) -> None:
        return None
