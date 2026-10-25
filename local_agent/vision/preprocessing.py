"""Configurable OpenCV preprocessing.

Each operation is optional so the pipeline can be benchmarked with
`python -m local_agent.vision.preprocessing --bench`.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict

import cv2
import numpy as np


@dataclass
class PreprocessConfig:
    grayscale: bool = True
    clahe: bool = True
    clahe_clip: float = 2.0
    clahe_grid: int = 8
    adaptive_threshold: bool = False
    block_size: int = 31  # must be odd
    c_offset: int = 12
    denoise: bool = False


class Preprocessor:
    def __init__(self, cfg: PreprocessConfig | None = None) -> None:
        self.cfg = cfg or PreprocessConfig()
        self._clahe = cv2.createCLAHE(clipLimit=self.cfg.clahe_clip, tileGridSize=(self.cfg.clahe_grid,) * 2)

    def run(self, bgr: np.ndarray) -> Dict[str, np.ndarray]:
        """Return a dict of images. 'gray' always exists. 'mask' exists when thresholding is on.

        The colour frame is passed through untouched because the DBNet detector
        expects a BGR image; gray / mask feed OCR and the fallback detector.
        """
        c = self.cfg
        out: Dict[str, np.ndarray] = {"bgr": bgr}
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if c.grayscale and bgr.ndim == 3 else (
            bgr if bgr.ndim == 2 else cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        )
        if c.denoise:
            gray = cv2.fastNlMeansDenoising(gray, None, 7, 7, 21)
        if c.clahe:
            gray = self._clahe.apply(gray)
        out["gray"] = gray
        if c.adaptive_threshold:
            bs = c.block_size if c.block_size % 2 == 1 else c.block_size + 1
            out["mask"] = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, bs, c.c_offset
            )
        return out


def benchmark(image: np.ndarray, runs: int = 30) -> Dict[str, float]:
    """Measure real per-frame cost of each configuration on the supplied image."""
    configs = {
        "gray": PreprocessConfig(clahe=False),
        "gray+clahe": PreprocessConfig(clahe=True),
        "gray+clahe+adaptive": PreprocessConfig(clahe=True, adaptive_threshold=True),
    }
    result = {}
    for name, cfg in configs.items():
        p = Preprocessor(cfg)
        p.run(image)  # warm-up
        t0 = time.perf_counter()
        for _ in range(runs):
            p.run(image)
        result[name] = round((time.perf_counter() - t0) * 1000 / runs, 2)
    return result


if __name__ == "__main__":
    import argparse

    from ..capture.demo_source import render_sample_page

    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", action="store_true")
    ap.add_argument("--image")
    args = ap.parse_args()
    img = cv2.imread(args.image) if args.image else render_sample_page()
    print({"image_shape": img.shape, "ms_per_frame": benchmark(img)})
