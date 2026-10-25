"""Dwell-time engine.

Decides when focus has stayed on one text region long enough to call the
learner stuck. The clock is injected (`now` argument) so behaviour is fully
deterministic in tests.

Rules
  * Focus enters a region          -> timer starts
  * Focus leaves for > grace       -> timer resets
  * Dwell reaches the threshold    -> emit STUCK once
  * Same region stays focused      -> no further events (no repeat triggering)
  * After a trigger the region is in cooldown, so re-entering it does not
    immediately trigger again.

Region identity survives small box jitter between OCR runs: two boxes are the
same target when their text matches (case-insensitive) and IoU is high.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple

from .geometry import bbox_iou


@dataclass(frozen=True)
class Target:
    text: str
    bbox: Tuple[int, int, int, int]

    def same_as(self, other: "Target", iou_min: float = 0.5) -> bool:
        return self.text.lower() == other.text.lower() and bbox_iou(self.bbox, other.bbox) >= iou_min


class DwellEvent(str, Enum):
    NONE = "none"
    FOCUS_STARTED = "focus_started"
    FOCUS_LOST = "focus_lost"
    STUCK = "stuck"


@dataclass
class DwellStatus:
    event: DwellEvent
    target: Optional[Target]
    dwell_s: float
    threshold_s: float
    in_cooldown: bool = False

    @property
    def progress(self) -> float:
        return 0.0 if self.threshold_s <= 0 else min(1.0, self.dwell_s / self.threshold_s)


class DwellEngine:
    def __init__(self, threshold_s: float = 1.5, cooldown_s: float = 6.0, grace_s: float = 0.15) -> None:
        if threshold_s <= 0:
            raise ValueError("threshold_s must be positive")
        self.threshold_s = threshold_s
        self.cooldown_s = cooldown_s
        self.grace_s = grace_s
        self._target: Optional[Target] = None
        self._since: float = 0.0
        self._lost_at: Optional[float] = None
        self._fired = False
        self._cooldowns: list[Tuple[Target, float]] = []  # (target, until)

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self._target, self._lost_at, self._fired = None, None, False

    def _in_cooldown(self, target: Target, now: float) -> bool:
        self._cooldowns = [(t, u) for (t, u) in self._cooldowns if u > now]
        return any(t.same_as(target) for t, _ in self._cooldowns)

    def update(self, target: Optional[Target], now: float) -> DwellStatus:
        thr = self.threshold_s

        # No focus right now
        if target is None:
            if self._target is None:
                return DwellStatus(DwellEvent.NONE, None, 0.0, thr)
            if self._lost_at is None:
                self._lost_at = now
            if now - self._lost_at <= self.grace_s:  # jitter tolerance
                return DwellStatus(DwellEvent.NONE, self._target, max(0.0, self._lost_at - self._since), thr, self._fired)
            self.reset()
            return DwellStatus(DwellEvent.FOCUS_LOST, None, 0.0, thr)

        # Focus on something
        if self._target is not None and self._target.same_as(target):
            self._lost_at = None
            self._target = target  # keep latest bbox
            dwell = now - self._since
            if not self._fired and dwell >= thr and not self._in_cooldown(target, now):
                self._fired = True
                self._cooldowns.append((target, now + self.cooldown_s))
                return DwellStatus(DwellEvent.STUCK, target, dwell, thr)
            return DwellStatus(DwellEvent.NONE, target, dwell, thr, self._fired or self._in_cooldown(target, now))

        # New target replaces the old one
        self._target, self._since, self._lost_at, self._fired = target, now, None, False
        return DwellStatus(DwellEvent.FOCUS_STARTED, target, 0.0, thr, self._in_cooldown(target, now))
