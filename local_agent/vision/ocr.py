"""OCR on detected regions. Returns word text, coordinates and confidence.

Engine: Tesseract through pytesseract (needs the tesseract binary installed).
Each detected region is cropped, upscaled when small, and read with
`image_to_data`, which yields per-word boxes that are mapped back into frame
coordinates. When Tesseract is not installed, a SimulationOcr fallback ensures
the demo pipeline runs without failing with ocr_unavailable.
"""
from __future__ import annotations

import abc
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple

import cv2
import numpy as np

from ..datatypes import TextRegion, WordBox

# Tesseract spawns OpenMP threads per call; one thread per process and several
# processes in parallel is measurably faster for many short line crops.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")


class OcrUnavailable(RuntimeError):
    pass


class OcrEngine(abc.ABC):
    name = "base"

    @abc.abstractmethod
    def read_regions(self, gray: np.ndarray, regions: List[TextRegion]) -> List[WordBox]: ...


_WORD_RE = re.compile(r"[A-Za-z0-9]")


class TesseractOcr(OcrEngine):
    name = "tesseract"

    def __init__(self, lang: str = "eng", min_height_px: int = 32, psm: int = 7) -> None:
        try:
            import pytesseract  # noqa: F401
        except ImportError as exc:
            raise OcrUnavailable("pytesseract is not installed") from exc
        self._pt = __import__("pytesseract")
        try:
            self._pt.get_tesseract_version()
        except Exception:
            candidates = [
                os.environ.get("TESSERACT_CMD"),
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"),
                os.path.expandvars(r"%PROGRAMFILES%\Tesseract-OCR\tesseract.exe"),
            ]
            found = False
            for cand in candidates:
                if cand and os.path.isfile(cand):
                    self._pt.pytesseract.tesseract_cmd = cand
                    try:
                        self._pt.get_tesseract_version()
                        found = True
                        break
                    except Exception:
                        pass
            if not found:
                raise OcrUnavailable("tesseract binary not found on PATH or standard installation directories")
        self.lang = lang
        self.min_height_px = min_height_px
        self.psm = psm
        self.workers = max(1, min(4, os.cpu_count() or 1))

    def _read_one(self, gray: np.ndarray, region: TextRegion, line_id: int) -> List[WordBox]:
        H, W = gray.shape[:2]
        x1, y1, x2, y2 = region.bbox
        x1, y1, x2, y2 = max(0, x1), max(0, y1), min(W, x2), min(H, y2)
        if x2 - x1 < 4 or y2 - y1 < 4:
            return []
        crop = gray[y1:y2, x1:x2]
        up = 1.0
        if crop.shape[0] < self.min_height_px:
            up = self.min_height_px / float(crop.shape[0])
            crop = cv2.resize(crop, None, fx=up, fy=up, interpolation=cv2.INTER_CUBIC)
        crop = cv2.copyMakeBorder(crop, 8, 8, 8, 8, cv2.BORDER_REPLICATE)
        data = self._pt.image_to_data(
            crop, lang=self.lang, config=f"--psm {self.psm}", output_type=self._pt.Output.DICT
        )
        words: List[WordBox] = []
        for i, raw in enumerate(data["text"]):
            text = (raw or "").strip()
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                continue
            if not text or conf < 0 or not _WORD_RE.search(text):
                continue
            bx = (data["left"][i] - 8) / up
            by = (data["top"][i] - 8) / up
            bw = data["width"][i] / up
            bh = data["height"][i] / up
            wb = (int(x1 + bx), int(y1 + by), int(x1 + bx + bw), int(y1 + by + bh))
            words.append(WordBox(text=text, bbox=wb, confidence=conf / 100.0, line_id=line_id))
        return words

    def read_regions(self, gray: np.ndarray, regions: List[TextRegion]) -> List[WordBox]:
        if not regions:
            return []
        jobs = [(gray, r, i) for i, r in enumerate(regions)]
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            results = list(pool.map(lambda a: self._read_one(*a), jobs))
        return [w for line in results for w in line]


class RapidOcrEngine(OcrEngine):
    """Real local OCR engine using rapidocr_onnxruntime (ONNX Runtime, no external binary)."""
    name = "rapid-ocr"

    def __init__(self, min_confidence: float = 0.45) -> None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:
            raise OcrUnavailable("rapidocr_onnxruntime is not installed") from exc
        self._ocr = RapidOCR()
        self.min_confidence = min_confidence

    def read_with_sentences(self, gray: np.ndarray, regions: Optional[List[TextRegion]] = None) -> Tuple[List[WordBox], List[dict]]:
        if gray is None or gray.size == 0:
            return [], []
        H, W = gray.shape[:2]
        try:
            results, _ = self._ocr(gray)
        except Exception:
            return [], []
        if not results:
            return [], []

        words: List[WordBox] = []
        sentences: List[dict] = []
        for line_id, item in enumerate(results):
            pts = item[0]
            raw_text = (item[1] or "").strip()
            try:
                conf = float(item[2])
            except (ValueError, TypeError):
                conf = 0.0

            if not raw_text or conf < self.min_confidence or not _WORD_RE.search(raw_text):
                continue

            min_x = max(0, min(int(round(p[0])) for p in pts))
            max_x = min(W, max(int(round(p[0])) for p in pts))
            min_y = max(0, min(int(round(p[1])) for p in pts))
            max_y = min(H, max(int(round(p[1])) for p in pts))

            if max_x - min_x < 4 or max_y - min_y < 4:
                continue

            matched_line_id = line_id
            if regions:
                mid_y = (min_y + max_y) / 2.0
                best_idx, best_dist = line_id, float("inf")
                for r_idx, r in enumerate(regions):
                    r_mid_y = (r.bbox[1] + r.bbox[3]) / 2.0
                    d = abs(r_mid_y - mid_y)
                    if d < best_dist:
                        best_dist, best_idx = d, r_idx
                matched_line_id = best_idx

            tokens = raw_text.split()
            if not tokens:
                continue

            line_words: List[WordBox] = []
            if len(tokens) == 1:
                tok = tokens[0]
                if _WORD_RE.search(tok):
                    wb = WordBox(text=tok, bbox=(min_x, min_y, max_x, max_y), confidence=conf, line_id=matched_line_id)
                    words.append(wb)
                    line_words.append(wb)
            else:
                total_chars = sum(len(t) for t in tokens) + (len(tokens) - 1) * 0.5
                line_w = max(10, max_x - min_x)
                char_w = line_w / max(1.0, total_chars)
                cur_x = float(min_x)
                for tok in tokens:
                    w_px = max(8.0, len(tok) * char_w)
                    wb = (
                        int(cur_x),
                        min_y,
                        int(min(max_x, cur_x + w_px)),
                        max_y,
                    )
                    if _WORD_RE.search(tok):
                        wbox = WordBox(text=tok, bbox=wb, confidence=conf, line_id=matched_line_id)
                        words.append(wbox)
                        line_words.append(wbox)
                    cur_x += w_px + (char_w * 0.5)

            if line_words:
                sentences.append({
                    "line_id": matched_line_id,
                    "text": raw_text,
                    "confidence": round(conf, 3),
                    "words": [w.to_dict() for w in line_words]
                })

        return words, sentences

    def read_regions(self, gray: np.ndarray, regions: Optional[List[TextRegion]] = None) -> List[WordBox]:
        return self.read_with_sentences(gray, regions)[0]


class NoOpOcr(OcrEngine):
    """Empty OCR engine returning no words."""
    name = "noop-ocr"

    def read_regions(self, gray: np.ndarray, regions: List[TextRegion]) -> List[WordBox]:
        return []


class SimulationOcr(OcrEngine):
    """Fallback OCR engine ONLY for demo mode when no real OCR engine is installed."""
    name = "simulation-ocr"

    def __init__(self, mode: str = "demo") -> None:
        self.mode = mode
        from ..capture.demo_source import SAMPLE_TITLE, SAMPLE_LINES
        self.sample_title = SAMPLE_TITLE
        self.sample_lines = SAMPLE_LINES

    def read_regions(self, gray: np.ndarray, regions: List[TextRegion]) -> List[WordBox]:
        if self.mode != "demo" or not regions:
            return []
        sorted_regions = sorted(regions, key=lambda r: (r.bbox[1], r.bbox[0]))
        words: List[WordBox] = []
        all_lines = [self.sample_title] + self.sample_lines

        for line_id, r in enumerate(sorted_regions):
            x1, y1, x2, y2 = r.bbox
            line_text = all_lines[line_id % len(all_lines)]
            tokens = line_text.split()
            if not tokens:
                continue
            total_chars = sum(len(t) for t in tokens) + len(tokens) - 1
            region_w = max(40, x2 - x1)
            char_w = region_w / max(1, total_chars)

            cur_x = float(x1)
            for tok in tokens:
                w_px = max(18.0, len(tok) * char_w * 1.05)
                wb = (int(cur_x), int(y1), int(min(x2, cur_x + w_px)), int(y2))
                words.append(WordBox(text=tok, bbox=wb, confidence=0.98, line_id=line_id))
                cur_x += w_px + (char_w * 0.75)
        return words


def create_ocr(lang: str = "eng", mode: str = "demo", **kwargs) -> Optional[OcrEngine]:
    """Return an OCR engine.

    1. Try TesseractOcr (if tesseract binary is installed).
    2. Try RapidOcrEngine (real local onnx OCR).
    3. If mode == "demo": fallback to SimulationOcr for demo sample page.
    4. Otherwise for camera/screen: return None to avoid fabricating words.
    """
    try:
        return TesseractOcr(lang=lang)
    except OcrUnavailable:
        pass

    try:
        return RapidOcrEngine()
    except OcrUnavailable:
        pass

    if mode == "demo":
        return SimulationOcr(mode="demo")
    return None

