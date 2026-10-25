"""Unit tests: geometry, dwell engine, state machine, schema, context."""
import threading

import pytest

from local_agent.agent.context import clean_word, extract_context
from local_agent.agent.state_machine import AgentStateMachine, State
from local_agent.cloud.schema import ValidationError, parse_assist_response, validate_assist_payload
from local_agent.datatypes import WordBox
from local_agent.focus.dwell_engine import DwellEngine, DwellEvent, Target
from local_agent.focus.geometry import bbox_iou, find_focused, point_in_bbox


# ---- geometry ---------------------------------------------------------
def test_brief_example_cursor_inside_box():
    assert point_in_bbox(400, 225, (300, 200, 500, 250))


def test_point_edges_outside_and_padding():
    box = (300, 200, 500, 250)
    assert point_in_bbox(300, 200, box) and point_in_bbox(500, 250, box)
    assert not point_in_bbox(299, 225, box)
    assert point_in_bbox(298, 225, box, padding=2)


def test_find_focused_prefers_smallest_and_handles_none():
    boxes = [(0, 0, 100, 100), (40, 40, 60, 60)]
    assert find_focused((50, 50), boxes) == 1
    assert find_focused(None, boxes) is None
    assert find_focused((500, 500), boxes) is None


def test_iou():
    assert bbox_iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert bbox_iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0


# ---- dwell ------------------------------------------------------------
W = Target("photosynthesis", (100, 100, 300, 130))
OTHER = Target("leaves", (400, 100, 480, 130))


def test_dwell_triggers_once_at_threshold():
    d = DwellEngine(1.5, cooldown_s=6, grace_s=0.15)
    assert d.update(W, 0.0).event == DwellEvent.FOCUS_STARTED
    assert d.update(W, 1.0).event == DwellEvent.NONE
    assert d.update(W, 1.49).event == DwellEvent.NONE
    assert d.update(W, 1.5).event == DwellEvent.STUCK
    for t in (1.6, 2.0, 5.0):  # no repeats while focus stays
        assert d.update(W, t).event == DwellEvent.NONE


def test_leaving_resets_timer_and_jitter_is_tolerated():
    d = DwellEngine(1.5, grace_s=0.15)
    d.update(W, 0.0)
    d.update(None, 1.0)               # brief loss inside grace
    assert d.update(W, 1.1).event == DwellEvent.NONE
    assert d.update(W, 1.5).event == DwellEvent.STUCK  # timer was not reset
    d2 = DwellEngine(1.5, grace_s=0.15)
    d2.update(W, 0.0)
    d2.update(None, 1.0)
    assert d2.update(None, 1.4).event == DwellEvent.FOCUS_LOST
    d2.update(W, 1.5)
    assert d2.update(W, 2.9).event == DwellEvent.NONE   # restarted at 1.5


def test_cooldown_blocks_retrigger_then_allows():
    d = DwellEngine(1.0, cooldown_s=6, grace_s=0.1)
    d.update(W, 0.0)
    assert d.update(W, 1.0).event == DwellEvent.STUCK
    d.update(None, 1.5); d.update(None, 2.0)
    d.update(W, 2.1)
    assert d.update(W, 4.0).event == DwellEvent.NONE     # cooldown until 7.0
    d.update(None, 4.5); d.update(None, 5.0)
    d.update(W, 8.0)
    assert d.update(W, 9.1).event == DwellEvent.STUCK


def test_different_word_and_box_jitter():
    d = DwellEngine(1.0)
    d.update(W, 0.0)
    assert d.update(Target("Photosynthesis", (102, 101, 302, 131)), 1.0).event == DwellEvent.STUCK  # same target
    assert d.update(OTHER, 1.1).event == DwellEvent.FOCUS_STARTED


def test_invalid_threshold():
    with pytest.raises(ValueError):
        DwellEngine(0)


# ---- state machine ----------------------------------------------------
def test_happy_path_and_labels():
    sm = AgentStateMachine()
    assert sm.label == "READY"
    assert sm.start() and sm.label == "READING"
    assert sm.focus_started() and sm.label == "FOCUS DETECTED"
    assert sm.stuck() and sm.begin_request() and sm.label == "ANALYZING"
    assert sm.assistance_ready() and sm.label == "ASSISTANCE READY"
    assert sm.assistance_done() and sm.state == State.READING


def test_duplicate_requests_are_rejected():
    sm = AgentStateMachine()
    sm.start(); sm.focus_started()
    assert sm.stuck()
    assert not sm.stuck()
    assert sm.begin_request()
    assert not sm.begin_request() and not sm.stuck()


def test_illegal_transitions_refused():
    sm = AgentStateMachine()
    assert not sm.stuck() and not sm.begin_request() and not sm.assistance_ready()
    sm.start()
    assert not sm.stuck()   # READING cannot jump to STUCK_WORD


def test_fail_and_recover_with_clock():
    now = [0.0]
    sm = AgentStateMachine(error_hold_s=3, clock=lambda: now[0])
    sm.start(); sm.focus_started(); sm.stuck(); sm.begin_request()
    sm.fail("timeout", "slow")
    assert sm.state == State.ERROR and sm.last_error == ("timeout", "slow")
    assert not sm.maybe_recover()
    now[0] = 3.1
    assert sm.maybe_recover() and sm.state == State.READING


def test_fail_from_idle_and_stop():
    sm = AgentStateMachine()
    sm.fail("x", "y")
    assert sm.state == State.ERROR
    sm.stop()
    assert sm.state == State.IDLE


def test_concurrent_stuck_yields_one_winner():
    sm = AgentStateMachine()
    sm.start(); sm.focus_started()
    results = []
    ts = [threading.Thread(target=lambda: results.append(sm.stuck())) for _ in range(20)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert results.count(True) == 1


# ---- schema -----------------------------------------------------------
def test_payload_valid_and_cleaned():
    assert validate_assist_payload({"word": " photosynthesis\x00 ", "context": "A  b\n c"}) == {
        "word": "photosynthesis", "context": "A b c"}


@pytest.mark.parametrize("payload,code", [
    ({"word": "", "context": "x"}, "empty_word"),
    ({"word": "two words", "context": "x"}, "invalid_word"),
    ({"word": "123", "context": "x"}, "invalid_word"),
    ({"word": "a" * 65, "context": "x"}, "invalid_word"),
    ({"word": "ok", "context": "  "}, "empty_context"),
    ({"word": "ok", "context": "x" * 601}, "context_too_long"),
    ({"word": 5, "context": "x"}, "invalid_payload"),
    ("nope", "invalid_payload"),
])
def test_payload_rejections(payload, code):
    with pytest.raises(ValidationError) as e:
        validate_assist_payload(payload)
    assert e.value.code == code


def test_response_parsing():
    ok = parse_assist_response({"status": "success", "word": "a", "definition": "d", "audio": "QQ==", "timings": {"bedrock_ms": 1}})
    assert ok.audio_b64 == "QQ==" and ok.timings["bedrock_ms"] == 1
    part = parse_assist_response({"status": "partial", "word": "a", "definition": "d", "audio": None})
    assert part.audio_b64 is None
    for bad in ({"status": "error", "error": {"code": "service_busy", "message": "m"}}, {"status": "success", "word": "a"},
                {"status": "success", "word": "a", "definition": "d", "audio": 5}, []):
        with pytest.raises(ValidationError):
            parse_assist_response(bad)


# ---- context ----------------------------------------------------------
def line(words, line_id, y, h=22, x0=90, conf=0.95):
    out, x = [], x0
    for w in words.split():
        out.append(WordBox(w, (x, y, x + 12 * len(w), y + h), conf, line_id))
        x += 12 * len(w) + 10
    return out


PAGE = (line("Plants and Light", 0, 100, h=45) + line("Photosynthesis is the process by which green plants", 1, 240)
        + line("make food. Leaves absorb sunlight.", 2, 290))


def test_sentence_spans_two_lines_and_heading_excluded():
    focus = next(w for w in PAGE if w.text == "Photosynthesis")
    ctx = extract_context(PAGE, focus)
    assert ctx.word == "Photosynthesis"
    assert ctx.context == "Photosynthesis is the process by which green plants make food."


def test_mid_sentence_word_and_extra_sentences():
    focus = next(w for w in PAGE if w.text == "absorb")
    assert extract_context(PAGE, focus).context == "Leaves absorb sunlight."
    assert "make food." in extract_context(PAGE, focus, extra_sentences=1).context


def test_truncation_keeps_word_and_punctuation_stripped():
    focus = next(w for w in PAGE if w.text == "process")
    assert "process" in extract_context(PAGE, focus, max_chars=40).context
    assert clean_word("(food.)") == "food"


def test_invalid_tokens_return_none():
    assert extract_context([WordBox("42", (0, 0, 10, 10), 0.9)], WordBox("42", (0, 0, 10, 10), 0.9)) is None
    assert extract_context([WordBox("a", (0, 0, 10, 10), 0.9)], WordBox("a", (0, 0, 10, 10), 0.9)) is None


def test_two_columns_do_not_mix():
    left = line("Left column sentence here.", 0, 100, x0=50)
    right = line("Right column other words.", 1, 100, x0=700)
    focus = left[1]
    assert "Right" not in extract_context(left + right, focus).context
