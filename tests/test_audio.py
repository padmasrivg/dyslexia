import base64
import sys
import threading
import time

import pytest

from local_agent.audio import audio_player as ap
from local_agent.audio.audio_player import AudioError, AudioPlayer, decode_audio

GOOD = base64.b64encode(b"\x01" * 200).decode()


def test_decode_valid():
    assert decode_audio(GOOD) == b"\x01" * 200


def test_decode_invalid_base64():
    with pytest.raises(AudioError):
        decode_audio("not base64 !!!")


def test_decode_too_small():
    with pytest.raises(AudioError):
        decode_audio(base64.b64encode(b"abc").decode())


def test_no_player_calls_on_error(monkeypatch):
    monkeypatch.setattr(ap, "_player_command", lambda p: None)
    msgs, ev = [], threading.Event()
    p = AudioPlayer(on_error=lambda m: (msgs.append(m), ev.set()))
    p.play_b64(GOOD)
    assert ev.wait(5) and "no audio player" in msgs[0]
    assert p.last_audio == b"\x01" * 200
    assert p.available() is False


def test_fake_command_calls_on_start(monkeypatch):
    monkeypatch.setattr(ap, "_player_command", lambda p: ["python3", "-c", "pass"])
    ev, errs = threading.Event(), []
    p = AudioPlayer(on_start=ev.set, on_error=errs.append)
    p.play_b64(GOOD)
    assert ev.wait(10) and errs == []


def test_never_blocks_caller(monkeypatch):
    monkeypatch.setattr(ap, "_player_command", lambda p: [sys.executable, "-c", "import time; time.sleep(3)"])
    started = threading.Event()
    p = AudioPlayer(on_start=started.set)
    t0 = time.perf_counter()
    p.play_b64(GOOD)
    assert time.perf_counter() - t0 < 0.5
    assert started.wait(5)
    p.stop()


def test_disabled_decodes_but_does_not_play(monkeypatch):
    monkeypatch.setattr(ap, "_player_command", lambda p: pytest.fail("must not run"))
    p = AudioPlayer(enabled=False)
    p.play_b64(GOOD)
    assert p.last_audio is not None
