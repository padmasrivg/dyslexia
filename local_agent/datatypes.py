"""Plain data types shared across the local agent."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

BBox = Tuple[int, int, int, int]  # x1, y1, x2, y2


@dataclass(frozen=True)
class TextRegion:
    """Output of the text detector: where text is, not what it says."""

    bbox: BBox
    confidence: float

    def to_dict(self) -> dict:
        return {"bbox": list(self.bbox), "confidence": round(self.confidence, 3)}


@dataclass(frozen=True)
class WordBox:
    """Output of OCR: one recognised word with its coordinates."""

    text: str
    bbox: BBox
    confidence: float
    line_id: int = 0

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "bbox": list(self.bbox),
            "confidence": round(self.confidence, 3),
            "line_id": self.line_id,
        }


@dataclass
class Frame:
    image: "object"  # numpy BGR array, already normalised in width
    scale: float  # processed_px / source_px
    origin: Tuple[int, int] = (0, 0)  # source-space top-left of the capture region
    source: str = "screen"  # screen | camera | demo
    captured_at: float = 0.0


@dataclass
class AssistanceResult:
    word: str
    definition: str
    audio_b64: Optional[str]
    source: str  # "aws" or "local-mock"
    api_latency_ms: float
    server_timings: dict = field(default_factory=dict)
