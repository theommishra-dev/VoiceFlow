#!/bin/zsh
# Removes VoiceFlow's login item, stops it, and deletes the generated files
# (.venv, models, VoiceFlow.app). Your vocab.txt is kept.
cd "${0:a:h}"
osascript -e 'tell application "System Events" to delete login item "VoiceFlow"' >/dev/null 2>&1 && echo "Login item removed."
pkill -f "$PWD/voiceflow.py" && echo "VoiceFlow stopped."
rm -rf .venv models VoiceFlow.app __pycache__ .voiceflow.lock
echo "Removed .venv, models and VoiceFlow.app."
echo "The downloaded fp16 model is in ~/.cache/huggingface/hub/models--mlx-community--whisper-large-v3-turbo (delete it if nothing else uses it)."
echo "Permissions can be removed in System Settings > Privacy & Security. Delete this folder to remove everything."
