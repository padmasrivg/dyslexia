import threading

import pytest

from local_agent.agent.state_machine import AgentStateMachine, InvalidTransition, State


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def to_state(sm, target):
    path = {
        State.IDLE: [], State.READING: ["start"], State.FOCUSING: ["start", "focus_started"],
        State.STUCK_WORD: ["start", "focus_started", "stuck"],
        State.REQUESTING_ASSISTANCE: ["start", "focus_started", "stuck", "begin_request"],
        State.ASSISTING: ["start", "focus_started", "stuck", "begin_request", "assistance_ready"],
    }[target]
    for step in path:
        assert getattr(sm, step)()


def test_legal_path_and_labels():
    sm = AgentStateMachine()
    assert (sm.state, sm.label) == (State.IDLE, "READY")
    sm.start(); assert sm.label == "READING"
    sm.focus_started(); assert sm.label == "FOCUS DETECTED"
    sm.stuck(); assert sm.state == State.STUCK_WORD and sm.label == "ANALYZING"
    sm.begin_request(); assert sm.state == State.REQUESTING_ASSISTANCE and sm.label == "ANALYZING"
    assert sm.busy()
    sm.assistance_ready(); assert sm.label == "ASSISTANCE READY"
    sm.assistance_done(); assert sm.state == State.READING and not sm.busy()


def test_duplicate_guards():
    sm = AgentStateMachine()
    to_state(sm, State.FOCUSING)
    assert sm.stuck() is True
    assert sm.stuck() is False
    assert sm.begin_request() is True
    assert sm.begin_request() is False
    assert sm.stuck() is False


def test_illegal_transitions_refused():
    sm = AgentStateMachine()
    assert not sm.stuck() and not sm.begin_request() and not sm.assistance_ready()
    assert not sm.focus_started() and not sm.assistance_done()
    sm.start()
    assert not sm.stuck() and not sm.assistance_ready()
    with pytest.raises(InvalidTransition):
        sm._go(State.ASSISTING)


@pytest.mark.parametrize("st", [State.IDLE, State.READING, State.FOCUSING, State.STUCK_WORD,
                                State.REQUESTING_ASSISTANCE, State.ASSISTING])
def test_fail_from_every_state(st):
    sm = AgentStateMachine()
    to_state(sm, st)
    sm.fail("timeout", "slow")
    assert sm.state == State.ERROR and sm.last_error == ("timeout", "slow")
    sm.fail("network", "again")  # already in ERROR
    assert sm.last_error[0] == "network"


def test_recover_after_hold():
    clk = Clock()
    sm = AgentStateMachine(error_hold_s=3.0, clock=clk)
    sm.start()
    sm.fail("x", "y")
    clk.t += 2.9
    assert not sm.maybe_recover() and sm.state == State.ERROR
    clk.t += 0.2
    assert sm.maybe_recover() and sm.state == State.READING


def test_new_failure_restarts_hold():
    clk = Clock()
    sm = AgentStateMachine(error_hold_s=3.0, clock=clk)
    sm.start(); sm.fail("a", "b")
    clk.t += 2.5
    sm.fail("a", "b")
    clk.t += 2.5
    assert not sm.maybe_recover()


def test_stop_from_anywhere():
    sm = AgentStateMachine()
    to_state(sm, State.REQUESTING_ASSISTANCE)
    sm.stop()
    assert sm.state == State.IDLE and sm.last_error is None
    sm.fail("a", "b"); sm.stop()
    assert sm.state == State.IDLE


def test_cancel_to_reading():
    sm = AgentStateMachine()
    to_state(sm, State.STUCK_WORD)
    assert sm.cancel_to_reading() and sm.state == State.READING
    assert not sm.cancel_to_reading()


def test_concurrent_stuck_yields_one_true():
    sm = AgentStateMachine()
    to_state(sm, State.FOCUSING)
    results, barrier = [], threading.Barrier(32)

    def go():
        barrier.wait()
        results.append(sm.stuck())

    ts = [threading.Thread(target=go) for _ in range(32)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert results.count(True) == 1 and len(results) == 32
