"""Microphone capture at 16 kHz mono float32 (what Whisper wants).

Every PortAudio call (open/start/stop/close) runs on one dedicated audio thread, never
on the caller's thread. Reason: PortAudio 19.7 on macOS can deadlock inside
stream.stop() (its start/stop listener on the CoreAudio IO thread and
AudioOutputUnitStop take the same two locks in opposite order). Reproduced on
12 Nov 2026: about 1 in 150-250 start/stop cycles under load. When that happens the
whole CoreAudio client in this process is dead (even a new stream hangs), so:

- stop() hands back the audio recorded so far straight away, without waiting for
  PortAudio, so the dictation is never lost and the caller (the main thread) never blocks;
- wedged() reports when a stop has been stuck for WEDGE_SECONDS, so the app
  can replace the process (see voiceflow.py restart()).
"""
import queue
import threading
import time

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
WEDGE_SECONDS = 3.0


def _open_stream(callback):
    return sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=callback)


class Recorder:
    def __init__(self, open_stream=_open_stream):
        self._open_stream = open_stream
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._recording = False
        self._stream = None
        self._jobs: queue.Queue = queue.Queue()
        self._stop_since: float | None = None  # set while stream.stop()/close() is running
        self.started = threading.Event()  # set once the mic is really open (for warm-up/tests)
        threading.Thread(target=self._worker, name="audio", daemon=True).start()

    # --- runs on the PortAudio callback thread --------------------------
    def _callback(self, indata, frames, time_info, status):
        with self._lock:
            if self._recording:
                self._chunks.append(indata[:, 0].copy())

    # --- runs on the audio thread ---------------------------------------
    def _worker(self):
        while True:
            job = self._jobs.get()
            try:
                if job == "start" and self._stream is None:
                    self._stream = self._open_stream(self._callback)
                    self._stream.start()
                    self.started.set()
                elif job == "stop" and self._stream is not None:
                    stream, self._stream = self._stream, None
                    self._stop_since = time.monotonic()
                    stream.stop()  # the call that can deadlock
                    stream.close()
            except Exception as exc:
                print(f"[VoiceFlow] microphone error ({job}): {exc}", flush=True)
                self._stream = None
            finally:
                self._stop_since = None

    # --- called from the main thread; never blocks on PortAudio -----------
    def start(self):
        with self._lock:
            self._chunks = []
            self._recording = True
        self.started.clear()
        self._jobs.put("start")

    def stop(self) -> np.ndarray:
        """Stop collecting and return the audio so far; the mic closes in the background."""
        with self._lock:
            self._recording = False
            audio = np.concatenate(self._chunks) if self._chunks else np.zeros(0, np.float32)
            self._chunks = []
        self._jobs.put("stop")
        return audio

    def wedged(self) -> bool:
        """True if stopping the mic has hung for WEDGE_SECONDS (audio is dead).
        Only stop is timed: start can legitimately wait on a macOS permission prompt."""
        since = self._stop_since
        return since is not None and time.monotonic() - since > WEDGE_SECONDS
