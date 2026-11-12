#!/bin/zsh
# Builds VoiceFlow.app next to this folder (needs Xcode Command Line Tools for clang).
# Only rebuild if launcher.c or Info.plist change: a rebuild changes the code signature,
# and macOS may then ask for Microphone/Accessibility/Input Monitoring again.
# Python changes (voiceflow.py etc.) never need a rebuild.
set -e
cd "${0:a:h}"
APP=../VoiceFlow.app
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
cp Info.plist "$APP/Contents/Info.plist"
clang -O2 -Wall -o "$APP/Contents/MacOS/VoiceFlow" launcher.c
codesign --force --sign - --identifier io.github.contactmishra.voiceflow "$APP"
echo "built ${APP:a}"
