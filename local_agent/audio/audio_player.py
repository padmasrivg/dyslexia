"""Non-blocking MP3 playback.

Playback runs in a daemon thread through an external player so the vision loop
never waits on audio. First available player wins: ffplay, mpg123, afplay (macOS),
or PowerShell MediaPlayer (Windows). If none exists the error is surfaced to the
UI instead of being swallowed.
"""
from __future__ import annotations

import base64
import binascii
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from typing import Callable, List, Optional


class AudioError(RuntimeError):
    pass


def decode_audio(b64: str) -> bytes:
    try:
        data = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AudioError("audio is not valid base64") from exc
    if len(data) < 64:
        raise AudioError("audio payload is too small to be an MP3")
    return data


def _player_command(path: str) -> Optional[List[str]]:
    if shutil.which("ffplay"):
        return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path]
    if shutil.which("mpg123"):
        return ["mpg123", "-q", path]
    if sys.platform == "darwin" and shutil.which("afplay"):
        return ["afplay", path]
    if sys.platform.startswith("win"):
        ps = (
            "Add-Type -AssemblyName presentationCore;$p=New-Object System.Windows.Media.MediaPlayer;"
            f"$p.Open([uri]'{path}');$p.Play();Start-Sleep -Milliseconds 400;"
            "while($p.NaturalDuration.HasTimeSpan -eq $false){Start-Sleep -Milliseconds 100};"
            "Start-Sleep -Seconds ([math]::Ceiling($p.NaturalDuration.TimeSpan.TotalSeconds))"
        )
        return ["powershell", "-NoProfile", "-Command", ps]
    return None


class AudioPlayer:
    def __init__(
        self,
        enabled: bool = True,
        on_error: Optional[Callable[[str], None]] = None,
        on_start: Optional[Callable[[], None]] = None,
    ) -> None:
        self.enabled = enabled
        self.on_error = on_error or (lambda msg: None)
        self.on_start = on_start or (lambda: None)
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self.last_audio: Optional[bytes] = None

    def available(self) -> bool:
        return _player_command("x.mp3") is not None

    def play_b64(self, b64: str) -> None:
        """Decode synchronously (fast, validates), play asynchronously."""
        data = decode_audio(b64)
        self.last_audio = data
        if not self.enabled:
            return
        threading.Thread(target=self._play_bytes, args=(data,), daemon=True).start()

    def _play_bytes(self, data: bytes) -> None:
        fd, path = tempfile.mkstemp(suffix=".mp3", prefix="assist_")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            cmd = _player_command(path)
            if cmd is None:
                self.on_error("no audio player found (install ffplay or mpg123)")
                return
            self.stop()
            with self._lock:
                self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                proc = self._proc
            self.on_start()
            code = proc.wait()
            if code not in (0, -15):  # -15: stopped on purpose
                self.on_error(f"audio player exited with code {code} (no output device?)")
        except Exception as exc:
            self.on_error(f"audio playback failed: {exc}")
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def stop(self) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
            self._proc = None
