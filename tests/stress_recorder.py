"""Manual stress test: open and close the real microphone many times while the CPU is busy.
This is how the PortAudio stop deadlock was reproduced (it hung within 2-500 cycles).

    ./.venv/bin/python tests/stress_recorder.py [cycles]

Not part of the unit tests: it uses the real microphone (macOS shows the orange dot).
"""
import multiprocessing
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import recorder  # noqa: E402


def burn():
    while True:
        sum(i * i for i in range(10000))


if __name__ == "__main__":
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    load = [multiprocessing.Process(target=burn, daemon=True) for _ in range(multiprocessing.cpu_count())]
    for p in load:
        p.start()
    r = recorder.Recorder()
    worst_stop, got_audio, t0 = 0.0, 0, time.time()
    for i in range(1, cycles + 1):
        r.start()
        if not r.started.wait(10):
            print(f"cycle {i}: microphone did not open within 10 s"); sys.exit(1)
        time.sleep(0.02 + (i % 7) * 0.03)
        t = time.time()
        got_audio += len(r.stop()) > 0
        worst_stop = max(worst_stop, time.time() - t)
        deadline = time.time() + 10
        while r._stream is not None or r._stop_since is not None or not r._jobs.empty():
            if r.wedged() or time.time() > deadline:
                print(f"cycle {i}: stop HUNG (deadlock) after {time.time() - t0:.0f} s"); sys.exit(1)
            time.sleep(0.002)
        if i % 100 == 0:
            print(f"{i} cycles ok", flush=True)
    print(f"OK: {cycles} cycles in {time.time() - t0:.0f} s, no hang; audio in {got_audio}; "
          f"slowest stop() call {worst_stop * 1000:.1f} ms")
