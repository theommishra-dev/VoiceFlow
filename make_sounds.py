"""Synthesise VoiceFlow's soft start/stop sounds (no copyright, no samples).

Soft rounded tones: pure sine + faint octave, slow-ish attack, gentle decay, low volume.
Tweak the numbers below and run:  ./.venv/bin/python make_sounds.py
"""
import wave
from pathlib import Path

import numpy as np

SR = 44100
OUT = Path(__file__).resolve().parent / "sounds"


def tone(f_from, f_to, dur=0.22, attack=0.025, peak=0.22):
    t = np.arange(int(SR * dur)) / SR
    # smooth pitch glide (ease-out)
    glide = 1 - (1 - np.clip(t / (dur * 0.6), 0, 1)) ** 2
    freq = f_from + (f_to - f_from) * glide
    phase = 2 * np.pi * np.cumsum(freq) / SR
    wave_ = np.sin(phase) + 0.12 * np.sin(2 * phase)
    env = np.exp(-t / (dur * 0.28))
    a = int(SR * attack)
    env[:a] *= 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, a))   # raised-cosine fade in
    env[-200:] *= np.linspace(1, 0, 200)                       # no click at the end
    return (wave_ * env / np.abs(wave_ * env).max() * peak).astype(np.float32)


def save(name, x):
    OUT.mkdir(exist_ok=True)
    with wave.open(str(OUT / name), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())


save("start.wav", tone(480, 640))   # soft rising "bloop": listening
save("stop.wav", tone(620, 460))    # soft falling "bloop": got it
print("wrote", *sorted(p.name for p in OUT.glob("*.wav")))
