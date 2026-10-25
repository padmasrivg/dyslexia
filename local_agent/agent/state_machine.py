"""Explicit agent state machine.

        IDLE -> READING -> FOCUSING -> STUCK_WORD -> REQUESTING_ASSISTANCE
                   ^                                          |
                   |                                          v
                   +------------- ASSISTING <-----------------+
        ERROR is reachable from every state and recovers to READING.

Its main job is to stop duplicate cloud requests: `stuck()` and
`begin_request()` return False unless the transition is legal, so a second
trigger while a request is in flight (or while assistance is showing) is
rejected here, not by scattered flags in the pipeline.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from enum import Enum
from typing import Deque, Dict, Optional, Set, Tuple


class State(str, Enum):
    IDLE = "IDLE"
    READING = "READING"
    FOCUSING = "FOCUSING"
    STUCK_WORD = "STUCK_WORD"
    REQUESTING_ASSISTANCE = "REQUESTING_ASSISTANCE"
    ASSISTING = "ASSISTING"
    ERROR = "ERROR"


ALLOWED: Dict[State, Set[State]] = {
    State.IDLE: {State.READING, State.ERROR},
    State.READING: {State.FOCUSING, State.IDLE, State.ERROR},
    State.FOCUSING: {State.READING, State.STUCK_WORD, State.IDLE, State.ERROR},
    State.STUCK_WORD: {State.REQUESTING_ASSISTANCE, State.READING, State.IDLE, State.ERROR},
    State.REQUESTING_ASSISTANCE: {State.ASSISTING, State.READING, State.IDLE, State.ERROR},
    State.ASSISTING: {State.READING, State.IDLE, State.ERROR},
    State.ERROR: {State.READING, State.IDLE},
}

# Plain text labels shown to the learner and in the UI
STATUS_LABEL: Dict[State, str] = {
    State.IDLE: "READY",
    State.READING: "READING",
    State.FOCUSING: "FOCUS DETECTED",
    State.STUCK_WORD: "ANALYZING",
    State.REQUESTING_ASSISTANCE: "ANALYZING",
    State.ASSISTING: "ASSISTANCE READY",
    State.ERROR: "ERROR",
}


class InvalidTransition(RuntimeError):
    pass


class AgentStateMachine:
    def __init__(self, error_hold_s: float = 3.0, clock=time.monotonic) -> None:
        self._lock = threading.RLock()
        self._state = State.IDLE
        self._clock = clock
        self._entered = clock()
        self.error_hold_s = error_hold_s
        self.last_error: Optional[Tuple[str, str]] = None  # (kind, message)
        self.history: Deque[Tuple[float, str, str]] = deque(maxlen=40)

    # ---- read side ----------------------------------------------------
    @property
    def state(self) -> State:
        with self._lock:
            return self._state

    @property
    def label(self) -> str:
        return STATUS_LABEL[self.state]

    def busy(self) -> bool:
        return self.state in (State.STUCK_WORD, State.REQUESTING_ASSISTANCE, State.ASSISTING)

    # ---- core transition ----------------------------------------------
    def _go(self, new: State, why: str = "") -> None:
        if new == self._state:
            return
        if new not in ALLOWED[self._state]:
            raise InvalidTransition(f"{self._state.value} -> {new.value} is not allowed")
        self.history.append((time.time(), f"{self._state.value}->{new.value}", why))
        self._state, self._entered = new, self._clock()

    def _try(self, new: State, why: str = "") -> bool:
        with self._lock:
            if new == self._state or new not in ALLOWED[self._state]:
                return False
            self._go(new, why)
            return True

    # ---- events -------------------------------------------------------
    def start(self) -> bool:
        return self._try(State.READING, "start")

    def stop(self) -> None:
        with self._lock:
            if self._state != State.IDLE:
                self._go(State.IDLE, "stop")
            self.last_error = None

    def focus_started(self) -> bool:
        with self._lock:
            return self._state == State.READING and self._try(State.FOCUSING, "focus started")

    def focus_lost(self) -> bool:
        with self._lock:
            return self._state == State.FOCUSING and self._try(State.READING, "focus lost")

    def stuck(self) -> bool:
        """True only for the one legal FOCUSING -> STUCK_WORD transition."""
        with self._lock:
            return self._state == State.FOCUSING and self._try(State.STUCK_WORD, "dwell threshold")

    def begin_request(self) -> bool:
        with self._lock:
            return self._state == State.STUCK_WORD and self._try(State.REQUESTING_ASSISTANCE, "request sent")

    def assistance_ready(self) -> bool:
        with self._lock:
            return self._state == State.REQUESTING_ASSISTANCE and self._try(State.ASSISTING, "response received")

    def assistance_done(self) -> bool:
        with self._lock:
            return self._state == State.ASSISTING and self._try(State.READING, "overlay expired")

    def cancel_to_reading(self, why: str = "cancelled") -> bool:
        with self._lock:
            return self._state in (State.STUCK_WORD, State.REQUESTING_ASSISTANCE) and self._try(State.READING, why)

    def fail(self, kind: str, message: str) -> None:
        with self._lock:
            self.last_error = (kind, message)
            if self._state != State.ERROR:
                self._go(State.ERROR, f"{kind}: {message}")
            else:
                self._entered = self._clock()

    def maybe_recover(self) -> bool:
        """Leave ERROR after a short hold so a transient failure never wedges the agent."""
        with self._lock:
            if self._state == State.ERROR and self._clock() - self._entered >= self.error_hold_s:
                return self._try(State.READING, "recovered")
            return False
