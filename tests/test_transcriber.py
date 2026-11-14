"""Checks for the text clean-up and for cutting long dictations (no model needed).
Run:  ./.venv/bin/python -m unittest discover tests
"""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import transcriber  # noqa: E402

SR = transcriber.SAMPLE_RATE


class SplitLongTest(unittest.TestCase):
    def test_short_audio_is_left_alone(self):
        audio = np.ones(20 * SR, np.float32)
        pieces = transcriber.split_long(audio)
        self.assertEqual(len(pieces), 1)
        self.assertEqual(len(pieces[0]), len(audio))

    def test_long_audio_is_cut_in_the_pause_and_nothing_is_lost(self):
        rng = np.random.default_rng(0)
        audio = rng.normal(0, 0.1, 70 * SR).astype(np.float32)
        audio[20 * SR:int(20.6 * SR)] = 0  # a pause at 20 s
        pieces = transcriber.split_long(audio)
        self.assertTrue(all(len(p) <= transcriber.MAX_PIECE * SR for p in pieces))
        self.assertEqual(sum(len(p) for p in pieces), len(audio))
        np.testing.assert_array_equal(np.concatenate(pieces), audio)
        self.assertTrue(20 * SR <= len(pieces[0]) <= 20.6 * SR, "first cut should land in the pause")


class CleanTest(unittest.TestCase):
    def test_fillers_and_spacing(self):
        self.assertEqual(transcriber.clean(" um, so the  test passed ."), "So the test passed.")

    def test_silence_hallucinations_are_dropped(self):
        self.assertEqual(transcriber.clean(" Thank you."), "")


class SlimTest(unittest.TestCase):
    def test_mlx_whisper_imports_without_numba_and_scipy(self):
        import mlx_whisper  # noqa: F401
        self.assertTrue(callable(sys.modules["numba"].jit))


if __name__ == "__main__":
    unittest.main()
