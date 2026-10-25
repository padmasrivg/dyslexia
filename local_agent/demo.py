"""Scripted pointer for the competition demo.

ONLY the pointer movement is scripted. Detection, OCR, dwell timing, the
state machine, the AWS request and the overlay all run for real. The UI
labels this as a simulated pointer.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from .agent.context import clean_word
from .pipeline import AssistantPipeline

TARGET = "photosynthesis"


def _find_target(pipeline: AssistantPipeline, wanted: str):
    words = pipeline.latest_words()
    for w in words:
        if clean_word(w.text).lower() == wanted:
            return w
    # OCR may misread a long word; fall back to the longest word of the first line
    first = [w for w in words if w.line_id == min((x.line_id for x in words), default=0)]
    return max(first, key=lambda w: len(w.text), default=None)


def run_demo_sweep(pipeline: AssistantPipeline, wanted: str = TARGET, timeout_s: float = 45.0) -> bool:
    """Blocking. Returns True when assistance was produced. Call from a thread."""
    pipeline.set_demo_running(True)
    try:
        t_end = time.monotonic() + timeout_s
        target = None
        while time.monotonic() < t_end and pipeline.running:
            target = _find_target(pipeline, wanted)
            if target:
                break
            time.sleep(0.1)
        if target is None:
            return False
        fw, fh = pipeline.frame_size()
        if not fw:
            return False
        tx = (target.bbox[0] + target.bbox[2]) / 2 / fw
        ty = (target.bbox[1] + target.bbox[3]) / 2 / fh
        sx, sy = 0.04, ty + 0.12  # start below the line, in the left margin
        steps = 24
        for i in range(steps + 1):  # approach: move toward the word like a hand would
            f = i / steps
            pipeline.set_focus(sx + (tx - sx) * f, sy + (ty - sy) * f)
            time.sleep(0.04)
        n_before = (pipeline.snapshot()["assistance"] or {}).get("id", 0)
        hold_until = time.monotonic() + 20.0
        while pipeline.running and time.monotonic() < hold_until:  # hold: real dwell time elapses here
            pipeline.set_focus(tx, ty)
            snap_a = pipeline.snapshot()["assistance"]
            if snap_a and snap_a["id"] > n_before:
                break
            time.sleep(0.05)
        got = bool(pipeline.snapshot()["assistance"] and pipeline.snapshot()["assistance"]["id"] > n_before)
        # keep the pointer on the word while the explanation is read, then release
        time.sleep(1.0)
        pipeline.set_focus(None, None)
        return got
    finally:
        pipeline.set_demo_running(False)


def start_demo_thread(pipeline: AssistantPipeline) -> Optional[threading.Thread]:
    if pipeline.snapshot()["demo"]["running"] or not pipeline.running:
        return None
    t = threading.Thread(target=run_demo_sweep, args=(pipeline,), daemon=True, name="demo-sweep")
    t.start()
    return t
