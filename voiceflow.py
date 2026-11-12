"""VoiceFlow: hold right Option, speak, release -> local Whisper text pasted at the cursor.

Normally started by VoiceFlow.app (login item). Dev run:  ./.venv/bin/python voiceflow.py
"""
import datetime
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import rumps
import Quartz
from AppKit import NSApplication, NSSound
from ApplicationServices import AXIsProcessTrusted, AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt

from hotkey import RightOptionHotkey
from paster import paste
from recorder import SAMPLE_RATE, Recorder
from transcriber import Transcriber

HERE = Path(__file__).resolve().parent
HISTORY = HERE / "history.log"
APP = HERE / "VoiceFlow.app"
SOUNDS = HERE / "sounds"
SOUND_VOLUME = 0.6
DEBUG = (HERE / ".debug").exists()  # touch .debug to log every key press


def debug(msg: str):
    if DEBUG:
        print(f"[VoiceFlow debug] {datetime.datetime.now():%H:%M:%S.%f} {msg}", flush=True)  # 0..1, on top of the already-quiet sound files
MIN_SECONDS = 0.4
SILENCE_PEAK = 0.005

ICONS = {"loading": "🎙…", "idle": "🎙", "recording": "🔴", "working": "⏳", "noperm": "🎙⚠️"}


_sounds = {}


def sound(name: str):
    """Play sounds/<name>.wav (soft synthesised tones, see make_sounds.py)."""
    if name not in _sounds:
        s = NSSound.alloc().initWithContentsOfFile_byReference_(str(SOUNDS / f"{name}.wav"), True)
        if s:
            s.setVolume_(SOUND_VOLUME)
        _sounds[name] = s
    s = _sounds[name]
    if s:
        s.stop()
        s.play()


def login_item_enabled() -> bool:
    out = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to get the name of every login item'],
        capture_output=True, text=True,
    ).stdout
    return "VoiceFlow" in out


def set_login_item(enabled: bool):
    if enabled:
        script = (
            'tell application "System Events" to make login item at end with properties '
            f'{{path:"{APP}", hidden:true}}'
        )
    else:
        script = f'tell application "System Events" to delete login item "VoiceFlow"'
    subprocess.run(["osascript", "-e", script], capture_output=True)


class VoiceFlowApp(rumps.App):
    def __init__(self):
        super().__init__("VoiceFlow", title=ICONS["loading"], quit_button=None)
        self.state = "loading"
        self.status_item = rumps.MenuItem("Loading Whisper model…")
        self.login_item = rumps.MenuItem("Start at login", callback=self.toggle_login)
        self.menu = [
            self.status_item,
            rumps.MenuItem("Hold right ⌥ Option to talk"),
            None,
            rumps.MenuItem("Edit vocabulary…", callback=self.open_vocab),
            rumps.MenuItem("Open history", callback=self.open_history),
            self.login_item,
            None,
            rumps.MenuItem("Quit VoiceFlow", callback=self.quit),
        ]
        self.recorder = Recorder()
        # Open the mic once at startup so the first real press is instant (the first open
        # in a new process can take ~3 s while macOS sets up audio and checks permission).
        self._audio_warm = threading.Event()
        threading.Thread(target=self._warm_audio, daemon=True).start()
        self.transcriber = Transcriber()
        self.started_at = 0.0
        self._restart_pending = False
        self.hotkey = RightOptionHotkey(self.on_press, self.on_release, self.on_cancel)
        self.hotkey_ok = self.hotkey.start()
        if not self.hotkey_ok:
            Quartz.CGRequestListenEventAccess()  # Input Monitoring prompt
        # Ask for Accessibility (needed to paste with Cmd+V); shows the system prompt once.
        ax = AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
        print(f"[VoiceFlow] {datetime.datetime.now():%Y-%m-%d %H:%M:%S} started. "
              f"hotkey(Input Monitoring)={self.hotkey_ok} paste(Accessibility)={bool(ax)}", flush=True)
        self.login_item.state = login_item_enabled()
        self._shown, self._perm_checked, self._ax_ok = None, 0.0, bool(ax)
        rumps.Timer(self.refresh, 0.25).start()

    # --- UI -------------------------------------------------------------
    def refresh(self, _):
        """Runs 4x a second but only touches the menu bar when something changed:
        redrawing the status item every tick cost ~20% CPU."""
        now = time.time()
        if self.recorder.wedged() and not self._restart_pending:
            # PortAudio deadlocked closing the mic (see recorder.py). Audio is dead in this
            # process; replace it, but let a transcription in progress paste first.
            self._restart_pending = True
            print("[VoiceFlow] microphone stop hung (PortAudio deadlock): restarting.", flush=True)
        if self._restart_pending and self.state != "working":
            restart()
        if self.state == "loading" and self.transcriber.ready.is_set() and self._audio_warm.is_set():
            self.state = "idle"
            print("[VoiceFlow] ready: hold right Option and speak.", flush=True)
        if now - self._perm_checked > 2:  # permission checks are cheap, but not free
            self._perm_checked = now
            if not self.hotkey_ok:
                self.hotkey_ok = self.hotkey.start()
            ax_now = bool(AXIsProcessTrusted())
            if ax_now and not self._ax_ok:
                # Permission was just granted: a tap made before that can stay deaf, so remake it.
                print("[VoiceFlow] Accessibility granted: re-installing the hotkey.", flush=True)
                self.hotkey.stop()
                self.hotkey_ok = self.hotkey.start()
            self._ax_ok = ax_now
        perms_ok = self.hotkey_ok and self._ax_ok
        key = self.state if perms_ok or self.state != "idle" else "noperm"
        if key == self._shown:
            return
        self._shown = key
        self.title = ICONS[key]
        self.status_item.title = {
            "loading": "Loading Whisper model…",
            "idle": "Ready",
            "recording": "Listening…",
            "working": "Transcribing…",
            "noperm": "Needs Accessibility / Input Monitoring permission",
        }[key]

    def open_vocab(self, _):
        subprocess.run(["open", "-t", str(HERE / "vocab.txt")])

    def open_history(self, _):
        HISTORY.touch()
        subprocess.run(["open", "-t", str(HISTORY)])

    def toggle_login(self, item):
        set_login_item(not item.state)
        item.state = login_item_enabled()

    def quit(self, _):
        rumps.quit_application()

    # --- push to talk ---------------------------------------------------
    def _warm_audio(self):
        t = time.time()
        self.recorder.start()
        if not self.recorder.started.wait(30):
            print("[VoiceFlow] microphone warm-up is slow (permission prompt?)", flush=True)
        time.sleep(0.05)
        self.recorder.stop()
        debug(f"audio warm-up {time.time() - t:.2f}s")
        self._audio_warm.set()

    def on_press(self):
        debug("on_press (state=%s)" % self.state)
        if self.state != "idle" or self._restart_pending:
            return
        self.recorder.start()  # opens the mic on the audio thread; never blocks here
        self.started_at = time.time()
        self.state = "recording"
        sound("start")

    def on_cancel(self):
        debug("on_cancel (state=%s)" % self.state)
        if self.state == "recording":
            self.recorder.stop()
            self.state = "idle"

    def on_release(self):
        debug("on_release (state=%s)" % self.state)
        if self.state != "recording":
            return
        audio = self.recorder.stop()
        seconds = len(audio) / SAMPLE_RATE
        debug(f"recorded {seconds:.2f}s, peak {np.abs(audio).max() if audio.size else 0:.4f}")
        if seconds < MIN_SECONDS or (audio.size and np.abs(audio).max() < SILENCE_PEAK):
            self.state = "idle"
            return
        sound("stop")
        self.state = "working"
        self.started_at = time.time()
        self.transcriber.submit(audio, lambda text: self.on_text(text, seconds))

    def on_text(self, text: str, seconds: float):
        took = time.time() - self.started_at
        if text:
            paste(text, can_type=AXIsProcessTrusted())
            with HISTORY.open("a") as f:
                f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  ({seconds:.1f}s audio, {took:.1f}s)  {text}\n")
        print(f"[VoiceFlow] {seconds:.1f}s audio -> {took:.1f}s: {text!r}", flush=True)
        self.state = "idle"


def restart():
    """Replace this process with a fresh copy (same PID, so the launcher does not count a
    crash). exec also ends the threads stuck in CoreAudio; the lock file is released
    because Python opens files close-on-exec."""
    sys.stdout.flush()
    os.execv(sys.executable, [sys.executable, "-u", str(HERE / "voiceflow.py")])


def single_instance_lock():
    """Two copies would paste every prompt twice, so refuse to start a second one."""
    import fcntl
    f = open(HERE / ".voiceflow.lock", "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("[VoiceFlow] already running (see the 🎙 in the menu bar).", flush=True)
        raise SystemExit(0)
    return f


if __name__ == "__main__":
    _lock = single_instance_lock()
    NSApplication.sharedApplication().setActivationPolicy_(1)  # menu bar only, no Dock icon
    VoiceFlowApp().run()
