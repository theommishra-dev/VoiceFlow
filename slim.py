"""Lets mlx-whisper run without numba, llvmlite and scipy (about 250 MB on disk).

mlx_whisper/timing.py imports numba and scipy when the package is loaded, but only uses
them for word-level timestamps, which VoiceFlow never asks for. If they are not
installed, put empty stand-ins in their place so the import works. Import this module
before mlx_whisper. If the real packages are installed, nothing happens.
"""
import importlib.util
import sys
import types


def _missing(name: str) -> bool:
    if name in sys.modules:
        return False
    try:
        return importlib.util.find_spec(name) is None
    except (ImportError, ValueError):
        return True


if _missing("numba"):
    numba = types.ModuleType("numba")
    numba.jit = lambda *args, **kwargs: (lambda fn: fn)  # @numba.jit(...) leaves the function as it is
    sys.modules["numba"] = numba

if _missing("scipy"):
    def _unavailable(*args, **kwargs):
        raise RuntimeError("word timestamps need scipy: pip install scipy numba")

    scipy = types.ModuleType("scipy")
    scipy.signal = types.ModuleType("scipy.signal")
    scipy.signal.medfilt = _unavailable
    sys.modules["scipy"] = scipy
    sys.modules["scipy.signal"] = scipy.signal
