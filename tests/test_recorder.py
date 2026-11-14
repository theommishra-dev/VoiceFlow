"""Regression test for the 12 Nov 2026 freeze: PortAudio's stream.stop() deadlocked on
the main thread and the whole app hung. Run:  ./.venv/bin/python -m unittest discover tests
"""
import sys
import threading
import time
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import recorder  # noqa: E402


class FakeStream:
    """Delivers one 0.1 s chunk on start; stop() blocks forever if hang=True (like the deadlock)."""

    def __init__(self, callback, hang):
        self.callback, self.hang = callback, hang

    def start(self):
        self.callback(np.full(1600, 0.5, np.float32))

    def stop(self):
        if self.hang:
            threading.Event().wait()

    def close(self):
        pass


def call_with_timeout(fn, seconds):
    out = {}
    t = threading.Thread(target=lambda: out.setdefault("v", fn()), daemon=True)
    t.start()
    t.join(seconds)
    return out.get("v", "TIMEOUT")


class RecorderTest(unittest.TestCase):
    def make(self, hang):
        try:
            return recorder.Recorder(open_stream=lambda cb: FakeStream(cb, hang))
        except TypeError:  # pre-fix Recorder: no injectable stream, patch sounddevice instead
            raise
            return recorder.Recorder()

    def test_stop_returns_audio_even_if_portaudio_hangs(self):
        r = self.make(hang=True)
        r.start()
        time.sleep(0.1)  # let the audio thread open the (fake) mic
        audio = call_with_timeout(r.stop, 1.0)
        self.assertIsNot(audio, "TIMEOUT", "Recorder.stop() blocked the caller (the freeze)")
        self.assertEqual(len(audio), 1600)

    def test_hung_stop_is_reported_as_wedged(self):
        recorder.WEDGE_SECONDS = 0.3
        r = self.make(hang=True)
        r.start()
        time.sleep(0.1)
        call_with_timeout(r.stop, 1.0)
        self.assertFalse(r.wedged())
        time.sleep(0.5)
        self.assertTrue(r.wedged())

    def test_normal_cycle_is_not_wedged(self):
        recorder.WEDGE_SECONDS = 0.3
        r = self.make(hang=False)
        for _ in range(3):
            r.start()
            time.sleep(0.05)
            self.assertEqual(len(r.stop()), 1600)
        time.sleep(0.5)
        self.assertFalse(r.wedged())


if __name__ == "__main__":
    unittest.main()
