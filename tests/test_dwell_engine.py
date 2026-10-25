import pytest

from local_agent.focus.dwell_engine import DwellEngine, DwellEvent, Target

W = Target("Photosynthesis", (90, 240, 298, 265))
OTHER = Target("carbon", (400, 330, 480, 355))


def eng(**kw):
    return DwellEngine(threshold_s=1.5, cooldown_s=6.0, grace_s=0.15, **kw)


def test_timer_starts_on_entry():
    e = eng()
    s = e.update(W, 10.0)
    assert s.event == DwellEvent.FOCUS_STARTED and s.dwell_s == 0.0


def test_no_stuck_before_threshold_and_once_at_threshold():
    e = eng()
    e.update(W, 0.0)
    assert e.update(W, 1.49).event == DwellEvent.NONE
    assert e.update(W, 1.5).event == DwellEvent.STUCK
    for t in (1.6, 3.0, 5.0):
        assert e.update(W, t).event == DwellEvent.NONE


def test_leaving_resets_but_grace_jitter_does_not():
    e = eng()
    e.update(W, 0.0)
    e.update(W, 1.0)
    assert e.update(None, 1.05).event == DwellEvent.NONE  # within grace
    assert e.update(W, 1.1).event == DwellEvent.NONE
    assert e.update(W, 1.5).event == DwellEvent.STUCK  # timer was kept

    e = eng()
    e.update(W, 0.0)
    e.update(None, 1.0)
    assert e.update(None, 1.3).event == DwellEvent.FOCUS_LOST
    assert e.update(W, 1.4).event == DwellEvent.FOCUS_STARTED
    assert e.update(W, 2.0).event == DwellEvent.NONE  # restarted at 1.4
    assert e.update(W, 2.9).event == DwellEvent.STUCK


def test_reentry_during_cooldown_does_not_retrigger():
    e = eng()
    e.update(W, 0.0)
    assert e.update(W, 1.5).event == DwellEvent.STUCK
    e.update(None, 1.6)
    e.update(None, 2.0)  # lost
    assert e.update(W, 2.1).in_cooldown
    for t in (3.0, 4.0, 6.0):
        assert e.update(W, t).event == DwellEvent.NONE


def test_different_word_triggers():
    e = eng()
    e.update(W, 0.0)
    assert e.update(W, 1.5).event == DwellEvent.STUCK
    assert e.update(OTHER, 1.6).event == DwellEvent.FOCUS_STARTED
    assert e.update(OTHER, 3.1).event == DwellEvent.STUCK


def test_same_word_after_cooldown_triggers_again():
    e = eng()
    e.update(W, 0.0)
    assert e.update(W, 1.5).event == DwellEvent.STUCK
    e.update(None, 2.0)
    e.update(None, 2.5)
    e.update(W, 8.0)  # cooldown (until 7.5) has elapsed
    assert e.update(W, 9.6).event == DwellEvent.STUCK


def test_box_jitter_is_same_target():
    e = eng()
    e.update(W, 0.0)
    jit = Target("photosynthesis", (92, 241, 300, 266))
    assert e.update(jit, 1.0).event == DwellEvent.NONE
    assert e.update(Target("Photosynthesis", (91, 240, 299, 265)), 1.5).event == DwellEvent.STUCK


def test_progress():
    e = eng()
    e.update(W, 0.0)
    assert e.update(W, 0.75).progress == pytest.approx(0.5)


@pytest.mark.parametrize("bad", [0, -1])
def test_invalid_threshold(bad):
    with pytest.raises(ValueError):
        DwellEngine(threshold_s=bad)
