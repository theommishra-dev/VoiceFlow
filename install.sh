#!/bin/zsh
# VoiceFlow installer. Run from the project folder:   ./install.sh
# Options:  --login   also start VoiceFlow automatically at every login
#           --no-open don't launch the app at the end
# Override the Python used with:  PYTHON=/path/to/python3.12 ./install.sh
set -e
cd "${0:a:h}"
LOGIN=0; OPEN=1
for arg in "$@"; do
  case $arg in --login) LOGIN=1 ;; --no-open) OPEN=0 ;; *) echo "unknown option $arg"; exit 1 ;; esac
done
say_step() { print -P "\n%F{cyan}==> $1%f"; }

say_step "Checking this Mac"
[[ $(uname -s) == Darwin && $(uname -m) == arm64 ]] || { echo "VoiceFlow needs an Apple Silicon Mac (M1 or newer)."; exit 1; }
xcode-select -p >/dev/null 2>&1 || { echo "Xcode Command Line Tools missing. Run: xcode-select --install   then run this again."; exit 1; }

if [[ -z $PYTHON ]]; then
  for c in python3.12 /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12; do
    command -v $c >/dev/null 2>&1 && { PYTHON=$(command -v $c); break; }
  done
fi
[[ -n $PYTHON ]] || { echo "Python 3.12 not found. Install it with:  brew install python@3.12   (or set PYTHON=...)"; exit 1; }
echo "Using $PYTHON ($($PYTHON --version))"

say_step "Creating the Python environment in .venv (about 350 MB)"
[[ -d .venv ]] || $PYTHON -m venv .venv
./.venv/bin/pip install -q --upgrade pip
# --no-deps: the pinned list is complete. It skips PyTorch (~630 MB), numba and scipy
# (~250 MB), which mlx-whisper lists as dependencies but never uses for transcription
# (see slim.py).
./.venv/bin/pip install -q --no-deps -r requirements.txt
rm -rf .venv/lib/python*/site-packages/PyObjCTest   # 16 MB of PyObjC's own tests

say_step "Preparing your vocabulary file"
[[ -f vocab.txt ]] || cp vocab.example.txt vocab.txt
echo "Edit vocab.txt to add names and jargon Whisper should spell right."

say_step "Getting the Whisper model (downloads ~1.6 GB once), making the 8-bit copy (~0.84 GB), deleting the download"
if [[ -f models/whisper-turbo-q8/weights.safetensors ]]; then
  echo "Already there."
else
  ./.venv/bin/python quantize_model.py 8 --tidy
fi

say_step "Building VoiceFlow.app"
[[ -f sounds/start.wav ]] || ./.venv/bin/python make_sounds.py
./app_src/build_app.sh

if (( LOGIN )); then
  say_step "Adding VoiceFlow to Login Items"
  ./.venv/bin/python -c "import voiceflow; voiceflow.set_login_item(True); print('Start at login:', voiceflow.login_item_enabled())"
fi

say_step "Done"
cat <<'MSG'
Next:
  1. VoiceFlow lives in your menu bar as 🎙 (no window, no Dock icon).
  2. macOS will ask for permissions for "VoiceFlow": allow Microphone, Accessibility
     and Input Monitoring (System Settings > Privacy & Security). If 🎙⚠️ shows, one is missing.
  3. Click into any text box, hold the RIGHT Option key, speak, let go.
MSG
(( OPEN )) && open VoiceFlow.app
exit 0
