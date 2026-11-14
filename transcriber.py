"""Local speech-to-text with mlx-whisper (large-v3-turbo, English).

All MLX work happens on ONE dedicated thread: MLX streams are per-thread,
so the model is loaded and used on the same worker.

Memory: the model (~0.8 GB) is dropped after IDLE_UNLOAD_SECONDS without a dictation
and loaded again the moment the key goes down, while you are still speaking
(about 0.3 s, so you don't notice it).
"""
import gc
import queue
import re
import threading
from pathlib import Path

import numpy as np

import slim  # noqa: F401  (must come before mlx_whisper is imported)

SAMPLE_RATE = 16000
MAX_PIECE = 28  # seconds; Whisper's window is 30
IDLE_UNLOAD_SECONDS = 300
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


def split_long(audio: np.ndarray) -> list[np.ndarray]:
    """Cut a long dictation into pieces of at most MAX_PIECE seconds, each cut at the
    quietest moment (a pause) in the second half of the piece.

    Whisper reads 30 s at a time and only the first 30 s would see the vocabulary prompt
    (mlx-whisper drops it for the following windows), so names and jargon said later in a
    long dictation were spelt wrong. Separate pieces each get the prompt."""
    pieces = []
    frame = int(0.2 * SAMPLE_RATE)
    while len(audio) > MAX_PIECE * SAMPLE_RATE:
        lo, hi = int(MAX_PIECE / 2 * SAMPLE_RATE), int(MAX_PIECE * SAMPLE_RATE)
        starts = np.arange(lo, hi - frame, frame // 2)
        energy = [float(np.square(audio[s:s + frame]).mean()) for s in starts]
        cut = int(starts[int(np.argmin(energy))]) + frame // 2
        pieces.append(audio[:cut])
        audio = audio[cut:]
    pieces.append(audio)
    return pieces


def transcribe_piece(audio: np.ndarray, prompt: str) -> str:
    import mlx_whisper

    result = mlx_whisper.transcribe(
        audio,
        path_or_hf_repo=MODEL,
        language="en",
        task="transcribe",
        initial_prompt=prompt or None,
        condition_on_previous_text=False,
        # Plain greedy decoding first; only if the result looks broken (a repetition loop
        # or very low confidence) Whisper tries again with a little randomness.
        temperature=(0.0, 0.2, 0.4),
        no_speech_threshold=0.6,
        verbose=None,
    )
    # Drop segments that still look like silence or a hallucination loop.
    kept = [
        seg["text"] for seg in result.get("segments", [])
        if seg.get("compression_ratio", 0) < 2.4
        and not (seg.get("no_speech_prob", 0) > 0.6 and seg.get("avg_logprob", 0) < -1.0)
        and seg.get("avg_logprob", 0) > -1.5
    ]
    text = clean(" ".join(kept))
    if text.lower().startswith("i'm talking about") and prompt[:40].lower() in (text.lower() + " "):
        return ""  # the vocabulary prompt leaked back out
    return text


def transcribe_array(audio: np.ndarray) -> str:
    import mlx.core as mx

    prompt = load_vocab()
    try:
        texts = [transcribe_piece(piece, prompt) for piece in split_long(audio.astype(np.float32))]
    finally:
        # Give back MLX's scratch buffers (~0.8 GB) so idle memory is just the model weights.
        mx.clear_cache()
    return " ".join(t for t in texts if t)


class Transcriber:
    """Background worker: submit(audio, callback) -> callback(text) on the worker thread."""

    def __init__(self):
        self._jobs: queue.Queue = queue.Queue()
        self.ready = threading.Event()
        threading.Thread(target=self._run, name="whisper", daemon=True).start()

    def submit(self, audio: np.ndarray, callback):
        self._jobs.put((audio, callback))

    def preload(self):
        """Call when a dictation starts: loads the model again if it was dropped."""
        self._jobs.put(None)

    def _load(self):
        import mlx.core as mx
        from mlx_whisper.transcribe import ModelHolder

        mx.eval(ModelHolder.get_model(MODEL, mx.float16).parameters())

    def _unload(self):
        import mlx.core as mx
        from mlx_whisper.transcribe import ModelHolder

        ModelHolder.model = ModelHolder.model_path = None
        gc.collect()
        mx.clear_cache()

    def _run(self):
        # Warm-up: loads weights into memory so the first real prompt is fast.
        transcribe_array(np.zeros(SAMPLE_RATE, dtype=np.float32))
        self.ready.set()
        while True:
            try:
                job = self._jobs.get(timeout=IDLE_UNLOAD_SECONDS)
            except queue.Empty:
                self._unload()
                job = self._jobs.get()
            if job is None:
                try:
                    self._load()
                except Exception as exc:
                    print(f"[VoiceFlow] model load error: {exc}", flush=True)
                continue
            audio, callback = job
            try:
                text = transcribe_array(audio)
            except Exception as exc:  # keep the worker alive
                print(f"[VoiceFlow] transcription error: {exc}", flush=True)
                text = ""
            callback(text)
