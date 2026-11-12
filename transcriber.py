"""Local speech-to-text with mlx-whisper (large-v3-turbo, English).

All MLX work happens on ONE dedicated thread: MLX streams are per-thread,
so the model is loaded and used on the same worker.
"""
import queue
import re
import threading
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
HERE = Path(__file__).resolve().parent
# 8-bit copy of whisper-large-v3-turbo (made by quantize_model.py): half the memory of the
# fp16 original, same accuracy in our tests (2026-11-12). Falls back to fp16 if missing.
_Q8 = HERE / "models" / "whisper-turbo-q8"
MODEL = str(_Q8) if (_Q8 / "weights.safetensors").exists() else "mlx-community/whisper-large-v3-turbo"
VOCAB_FILE = HERE / "vocab.txt"

# Phrases Whisper invents on near-silence.
HALLUCINATIONS = {
    "thank you.", "thank you", "thanks for watching.", "thanks for watching!",
    "you", "bye.", "bye", ".", "okay.", "so",
}
FILLERS = re.compile(r"(?<![\w'])(um+|uh+|erm+|hmm+|ah+)(?![\w'])[,.]?\s*", re.IGNORECASE)


def load_vocab() -> str:
    """vocab.txt: one term per line, '#' comments. Becomes Whisper's prompt."""
    if not VOCAB_FILE.exists():
        example = HERE / "vocab.example.txt"
        if not example.exists():
            return ""
        VOCAB_FILE.write_text(example.read_text())
    words = [
        line.strip() for line in VOCAB_FILE.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    # A natural sentence works better than a bare list and is less likely to leak into output.
    return ("I'm talking about " + ", ".join(words) + ".") if words else ""


def clean(text: str) -> str:
    text = FILLERS.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.?!])", r"\1", text)
    if text.lower() in HALLUCINATIONS:
        return ""
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


def transcribe_array(audio: np.ndarray) -> str:
    import mlx.core as mx
    import mlx_whisper

    result = mlx_whisper.transcribe(
        audio.astype(np.float32),
        path_or_hf_repo=MODEL,
        language="en",
        task="transcribe",
        initial_prompt=load_vocab() or None,
        condition_on_previous_text=False,
        temperature=0.0,
        no_speech_threshold=0.6,
        verbose=None,
    )
    # Give back MLX's scratch buffers (~0.8 GB) so idle memory is just the model weights.
    mx.clear_cache()
    # Drop segments that look like silence or a hallucination loop.
    kept = [
        seg["text"] for seg in result.get("segments", [])
        if seg.get("compression_ratio", 0) < 2.4
        and not (seg.get("no_speech_prob", 0) > 0.6 and seg.get("avg_logprob", 0) < -1.0)
        and seg.get("avg_logprob", 0) > -1.5
    ]
    text = clean(" ".join(kept))
    if text.lower().startswith("i'm talking about") and load_vocab()[:40].lower() in (text.lower() + " "):
        return ""  # the vocabulary prompt leaked back out
    return text


class Transcriber:
    """Background worker: submit(audio, callback) -> callback(text) on the worker thread."""

    def __init__(self):
        self._jobs: queue.Queue = queue.Queue()
        self.ready = threading.Event()
        threading.Thread(target=self._run, name="whisper", daemon=True).start()

    def submit(self, audio: np.ndarray, callback):
        self._jobs.put((audio, callback))

    def _run(self):
        # Warm-up: loads weights into memory so the first real prompt is fast.
        transcribe_array(np.zeros(SAMPLE_RATE, dtype=np.float32))
        self.ready.set()
        while True:
            audio, callback = self._jobs.get()
            try:
                text = transcribe_array(audio)
            except Exception as exc:  # keep the worker alive
                print(f"[VoiceFlow] transcription error: {exc}", flush=True)
                text = ""
            callback(text)
