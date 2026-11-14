"""Microphone capture at 16 kHz mono float32 (what Whisper wants), with Apple's AVAudioEngine.

A fresh engine is made for every dictation, so it always uses the microphone that is the
system default right now (AirPods just connected, a headset just unplugged), at whatever
sample rate that device runs; AVAudioConverter turns it into 16 kHz mono.

History: until 14 Nov 2026 this used PortAudio (sounddevice). PortAudio 19.7 can deadlock
inside stream.stop() on macOS, and in real use that hit about 1 dictation in 29, each one
costing an app restart. AVAudioEngine does not have that problem (see
tests/stress_recorder.py), but the safety net stays:

- every engine call (open/start/stop) runs on one dedicated audio thread, never on the
  caller's thread, so the main thread can never hang on audio;
- stop() hands back the audio recorded so far without waiting for the engine to close;
- wedged() reports a stop that has been stuck for WEDGE_SECONDS, so the app can replace
  the process (see voiceflow.py restart()).
"""
import queue
import threading
import time

import numpy as np

SAMPLE_RATE = 16000
WEDGE_SECONDS = 3.0
TAIL_SECONDS = 0.15  # the engine delivers audio in ~0.1 s blocks; wait this long for the last one


class _EngineStream:
    """One open microphone. callback(samples) gets 16 kHz mono float32 arrays."""

    def __init__(self, callback):
        import AVFoundation as AV  # imported here so tests with a fake stream don't need it

        self._AV = AV
        self._callback = callback
        self._engine = AV.AVAudioEngine.alloc().init()
        self._input = self._engine.inputNode()
        hw = self._input.outputFormatForBus_(0)
        if hw.sampleRate() <= 0 or hw.channelCount() == 0:
            raise RuntimeError("no microphone found")
        self._rate = hw.sampleRate()
        self._out = AV.AVAudioFormat.alloc().initWithCommonFormat_sampleRate_channels_interleaved_(
            AV.AVAudioPCMFormatFloat32, float(SAMPLE_RATE), 1, False
        )
        self._converter = AV.AVAudioConverter.alloc().initFromFormat_toFormat_(hw, self._out)
        if self._converter is None:
            raise RuntimeError(f"cannot convert microphone format {hw}")
        self._input.installTapOnBus_bufferSize_format_block_(0, 1024, hw, self._tap)
        self._engine.prepare()

    def _tap(self, buf, when):
        """Runs on an AVAudioEngine thread for every block of microphone audio."""
        try:
            AV = self._AV
            capacity = int(buf.frameLength() * SAMPLE_RATE / self._rate) + 64
            out = AV.AVAudioPCMBuffer.alloc().initWithPCMFormat_frameCapacity_(self._out, capacity)
            fed = [False]

            def feed(packets, status):
                if fed[0]:
                    return None, AV.AVAudioConverterInputStatus_NoDataNow
                fed[0] = True
                return buf, AV.AVAudioConverterInputStatus_HaveData

            self._converter.convertToBuffer_error_withInputFromBlock_(out, None, feed)
            n = out.frameLength()
            if n:
                data = out.floatChannelData()[0].as_buffer(n * 4)
                self._callback(np.frombuffer(data, dtype=np.float32, count=n).copy())
        except Exception as exc:  # never let an exception escape into Core Audio
            print(f"[VoiceFlow] microphone error (tap): {exc}", flush=True)

    def start(self):
        ok, err = self._engine.startAndReturnError_(None)
        if not ok:
            raise RuntimeError(f"microphone did not start: {err}")

    def stop(self):
        self._engine.stop()

    def close(self):
        self._input.removeTapOnBus_(0)
        self._engine = self._input = self._converter = None


def _open_stream(callback):
    return _EngineStream(callback)


class Recorder:
    def __init__(self, open_stream=_open_stream):
        self._open_stream = open_stream
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._recording = False
        self._chunk_arrived = threading.Event()
        self._stream = None
        self._jobs: queue.Queue = queue.Queue()
        self._stop_since: float | None = None  # set while stream.stop()/close() is running
        self.started = threading.Event()  # set once the mic is really open (for warm-up/tests)
        self.failed = threading.Event()  # set if the last open failed (no microphone, ...)
        threading.Thread(target=self._worker, name="audio", daemon=True).start()

    # --- runs on the audio engine's thread --------------------------------
    def _callback(self, samples):
        with self._lock:
            if self._recording:
                self._chunks.append(samples)
        self._chunk_arrived.set()

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
                    stream.stop()
                    stream.close()
            except Exception as exc:
                print(f"[VoiceFlow] microphone error ({job}): {exc}", flush=True)
                self._stream = None
                if job == "start":
                    self.failed.set()
            finally:
                self._stop_since = None

    # --- called from the main thread; never blocks on the audio engine ----
    def start(self):
        with self._lock:
            self._chunks = []
            self._recording = True
        self.started.clear()
        self.failed.clear()
        self._jobs.put("start")

    def seconds(self) -> float:
        """Length recorded so far."""
        with self._lock:
            return sum(len(c) for c in self._chunks) / SAMPLE_RATE

    def stop(self, tail: bool = False) -> np.ndarray:
        """Stop collecting and return the audio so far; the mic closes in the background.
        tail=True first waits (at most TAIL_SECONDS) for the block that is still being
        filled, so the end of the last word is not cut off."""
        if tail and self.started.is_set():
            self._chunk_arrived.clear()
            self._chunk_arrived.wait(TAIL_SECONDS)
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
