# VoiceFlow 🎙

**Free, private, push-to-talk dictation for Apple Silicon Macs.**
Hold the right Option key, speak, let go. About a second later your words are typed
wherever your cursor is: a terminal running Claude Code or ChatGPT, your browser, Notes,
Slack, anything.

Everything runs on your Mac with OpenAI's Whisper model (large-v3-turbo) on the Apple
GPU through [MLX](https://github.com/ml-explore/mlx). No account, no subscription, no
internet needed after setup, and your voice never leaves the machine.

It was built as a homemade alternative to paid dictation apps, mainly for talking to AI
coding assistants instead of typing long prompts.

---

## What it lets you do

- **Dictate anywhere.** Hold right ⌥ Option, talk, release. The text is pasted at the cursor
  in any app. You still press Enter yourself, so nothing is sent by accident.
- **Fast.** About 1.3 s from releasing the key to text on screen for a typical prompt
  (measured on a base M2 MacBook with 8 GB of RAM).
- **Accurate with accents.** Uses Whisper large-v3-turbo, one of the best open speech
  models, tuned here for English. Tested with Indian-English voices.
- **Spells your jargon right.** Put names, products and technical words in `vocab.txt`
  and Whisper will use those spellings.
- **Cleans up the text.** Drops "um" and "uh", fixes spacing and capitalisation, and filters
  out the phantom phrases Whisper sometimes invents on silence ("Thank you.").
- **Stays out of your way.** Lives in the menu bar (no window, no Dock icon), can start at
  login, restarts itself if it crashes, and keeps your clipboard as it was.
- **Light.** 0.1% CPU while idle, about 1 GB of memory (the model), about 1.5 GB on disk.
- **Soft sounds.** A gentle rising tone when it starts listening, a falling one when it is
  done. The tones are synthesised by a small script, so you can change them.

### Menu bar

| Icon | Meaning |
|---|---|
| 🎙… | Loading the model (a few seconds after start) |
| 🎙 | Ready |
| 🔴 | Listening (right Option is held) |
| ⏳ | Transcribing |
| 🎙⚠️ | A permission is missing (see [Permissions](#permissions)) |

The menu also has: **Edit vocabulary…**, **Open history** (everything you dictated, with
timings), **Start at login** and **Quit VoiceFlow**.

---

## Requirements

- A Mac with **Apple Silicon** (M1, M2, M3, M4 or newer). Intel Macs are not supported (MLX needs Apple Silicon).
- macOS 13 Ventura or newer.
- **Python 3.12**, for example from [Homebrew](https://brew.sh): `brew install python@3.12`
- **Xcode Command Line Tools** (to build the small app launcher): `xcode-select --install`
- About **2.5 GB free disk** during install (1.6 GB model download + 0.84 GB compact copy + 0.6 GB Python packages).
  After install you can delete the 1.6 GB download if you like (see [Uninstall](#uninstall)).
- 8 GB of RAM is enough.

---

## Install

```bash
# 1. Get the code
git clone https://github.com/contactmishra/VoiceFlow.git
cd VoiceFlow

# 2. Install (creates .venv, downloads and compresses the model, builds VoiceFlow.app)
./install.sh            # add --login to also start it automatically at every login
```

The installer:
1. checks that this is an Apple Silicon Mac with the Xcode tools and Python 3.12,
2. creates a private Python environment in `.venv/` (nothing is installed system-wide),
3. copies `vocab.example.txt` to your own `vocab.txt`,
4. downloads `mlx-community/whisper-large-v3-turbo` once (1.6 GB) and saves an
   8-bit copy in `models/whisper-turbo-q8` (0.84 GB, same accuracy in our tests, half the memory),
5. builds `VoiceFlow.app` in the project folder and opens it.

Everything VoiceFlow creates stays inside the project folder, apart from the model download
cache in `~/.cache/huggingface` and the optional Login Item.

### Permissions

The first time it runs, macOS asks for three permissions for **VoiceFlow**. Allow all three
in **System Settings > Privacy & Security**:

| Permission | Why |
|---|---|
| **Microphone** | to hear you while you hold the key |
| **Input Monitoring** | to notice the right Option key |
| **Accessibility** | to paste the text with ⌘V |

If you skip Accessibility, VoiceFlow still works but leaves the text on the clipboard for
you to paste yourself. The first line of `voiceflow.log` after each start shows which
permissions are on.

---

## Use

1. Click into any text box (for example the Claude Code prompt in Terminal).
2. **Hold the right ⌥ Option key** and speak.
3. Let go. The text appears about a second later. Check it, then press Enter.

Tips:
- Recordings shorter than 0.4 s are ignored, so a stray tap does nothing.
- Pressing another key while holding right Option (an Option shortcut such as ⌥E) cancels
  the recording, so your normal Option shortcuts keep working.
- Long prompts are fine: a 15-second sentence takes about 1.4 s.
- Start or restart it any time by double-clicking `VoiceFlow.app` in the project folder.

---

## Customise

| What | Where |
|---|---|
| Words Whisper should spell right | `vocab.txt` (one per line; applies to your next prompt, no restart) |
| Sound volume | `SOUND_VOLUME` in `voiceflow.py` |
| The sounds themselves | edit the tones in `make_sounds.py`, then `./.venv/bin/python make_sounds.py` |
| Minimum recording length, silence threshold | `MIN_SECONDS`, `SILENCE_PEAK` in `voiceflow.py` |
| The hotkey | `RIGHT_OPTION_KEYCODE` / `NX_DEVICERALTKEYMASK` in `hotkey.py` (e.g. right ⌘ is keycode 54, mask `0x10`) |
| Language | `language="en"` in `transcriber.py` (Whisper supports ~100 languages; `None` = auto-detect) |
| Smaller model (saves 0.4 GB RAM) | `./.venv/bin/python quantize_model.py 4`, then point `_Q8` in `transcriber.py` at `models/whisper-turbo-q4` |

After editing Python files, quit VoiceFlow from the menu bar and open `VoiceFlow.app` again.
You only need `./app_src/build_app.sh` if you change `app_src/launcher.c` or `app_src/Info.plist`
(macOS may then ask for the permissions again, because the app's signature changes).

---

## How it works

```
 hold right ⌥ ──► hotkey.py ──► recorder.py ──► release ──► transcriber.py ──► paster.py
 (Quartz event tap,   (mic, 16 kHz mono)          (Whisper large-v3-turbo,    (clipboard + ⌘V,
  listen-only)                                     8-bit, on the GPU via MLX)   then restores
                                                                                your clipboard)
```

| File | Role |
|---|---|
| `voiceflow.py` | Menu-bar app (rumps): states, sounds, history, login item |
| `hotkey.py` | Listen-only Quartz event tap for the right Option key; cancels on Option shortcuts |
| `recorder.py` | Microphone capture with `sounddevice` at 16 kHz mono |
| `transcriber.py` | Loads Whisper once on a dedicated thread, transcribes, cleans text, filters hallucinations, frees GPU scratch memory |
| `paster.py` | Pastes via the clipboard and ⌘V, then puts your old clipboard back |
| `app_src/launcher.c`, `Info.plist`, `build_app.sh` | A tiny native `VoiceFlow.app` that starts the Python app as its child, so macOS shows "VoiceFlow" in permission prompts, and restarts it if it crashes |
| `quantize_model.py` | Makes the 8-bit (or 4-bit) copy of the model from the Hugging Face download |
| `make_sounds.py` | Synthesises the soft start/stop tones in `sounds/` |
| `install.sh`, `uninstall.sh` | Set up and remove everything |
| `vocab.example.txt` | Starter vocabulary (your own `vocab.txt` is git-ignored) |

### Performance (base M2, 8 GB, macOS 27)

| | Value |
|---|---|
| Idle CPU | 0.1%, about 3 wake-ups per second |
| Memory | about 1.0 GB (0.84 GB is the model) |
| Time per prompt | about 1.3 s for 4 to 15 s of speech, about 0.15 s of CPU (the rest is GPU) |
| Accuracy | 3.7% word error rate on 8 Indian-English test prompts; every error was formatting (5k vs five K, Summarize vs Summarise). fp16, 8-bit and 4-bit models scored the same |
| First prompt after start | 3 to 5 s while the GPU warms up |
| Disk | `.venv` 0.62 GB, `models/` 0.84 GB, plus the 1.6 GB download cache |

---

## Privacy

- Audio is recorded only while you hold the key, kept in memory, transcribed locally and
  thrown away. It is never written to disk or sent anywhere.
- The text of each dictation is saved locally in `history.log` (git-ignored) so you can
  find something you said. Delete the file whenever you like.
- The only network access is the one-time model download from Hugging Face during install.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| 🎙⚠️ in the menu bar | Turn on VoiceFlow under Accessibility and Input Monitoring in System Settings > Privacy & Security, then reopen the app |
| Nothing happens when holding right Option | Check Input Monitoring; check `voiceflow.log`; make sure you hold the **right** Option key |
| Text appears on the clipboard but is not pasted | Accessibility is off for VoiceFlow |
| The first dictation is empty | macOS was showing the Microphone prompt; allow it and try again |
| A word is always wrong | Add it to `vocab.txt` |
| No 🎙 after double-clicking the app | Look at `voiceflow.log` in the project folder; run `./install.sh` again if `.venv` is missing |
| Permissions keep coming back after a rebuild | Expected after `build_app.sh`; remove the old VoiceFlow entries in System Settings and allow again |

---

## Uninstall

```bash
./uninstall.sh      # removes the login item, stops the app, deletes .venv, models and VoiceFlow.app
```

Then delete the project folder. To also free the 1.6 GB model download:
`rm -rf ~/.cache/huggingface/hub/models--mlx-community--whisper-large-v3-turbo`
(only if no other tool uses it). Permissions can be removed in System Settings > Privacy & Security.

---

## Fork it, change it

1. Click **Fork** on GitHub, then clone your fork and run `./install.sh`.
2. Change the bundle identifier in `app_src/Info.plist` and `app_src/build_app.sh`
   (`io.github.contactmishra.voiceflow`) to your own, for example `io.github.<you>.voiceflow`.
3. Ideas: a different hotkey, other languages or auto-detect, a "send Enter after paste"
   option, AI clean-up of the text, a waveform in the menu bar, an Intel build with
   whisper.cpp.

Pull requests and issues are welcome.

---

## Credits and licence

- [Whisper](https://github.com/openai/whisper) by OpenAI (MIT), the speech model.
- [MLX](https://github.com/ml-explore/mlx) and [mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) by Apple (MIT); model weights from [mlx-community](https://huggingface.co/mlx-community/whisper-large-v3-turbo).
- [rumps](https://github.com/jaredks/rumps) (BSD), [sounddevice](https://github.com/spatialaudio/python-sounddevice) (MIT), [PyObjC](https://github.com/ronaldoussoren/pyobjc) (MIT).

VoiceFlow itself is released under the [MIT licence](LICENSE).
Not affiliated with Voiceflow Inc., Wispr or OpenAI.
