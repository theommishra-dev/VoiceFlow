"""Paste text into whatever app has focus: clipboard + Cmd+V, then restore clipboard.

Privacy: the dictated text is put on the clipboard for this Mac only (no Universal
Clipboard / Handoff to your other devices) and marked transient + concealed, the
nspasteboard.org convention that clipboard managers (Raycast, Alfred, Paste, Maccy...)
honour by not saving it. After pasting, the text is taken off the clipboard again.
"""
import time

import Quartz
from AppKit import NSPasteboard, NSPasteboardTypeString

V_KEYCODE = 9
CURRENT_HOST_ONLY = 1  # NSPasteboardContentsCurrentHostOnly: never synced to other devices
PRIVATE_MARKERS = ("org.nspasteboard.TransientType", "org.nspasteboard.ConcealedType")


def _cmd_v():
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    for down in (True, False):
        ev = Quartz.CGEventCreateKeyboardEvent(src, V_KEYCODE, down)
        Quartz.CGEventSetFlags(ev, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def put_private(pb, text: str):
    """Put text on pasteboard pb: this Mac only, and flagged so clipboard managers skip it."""
    pb.prepareForNewContentsWithOptions_(CURRENT_HOST_ONLY)
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)
    for marker in PRIVATE_MARKERS:
        pb.setString_forType_("", marker)


def paste(text: str, can_type: bool = True):
    """can_type=False (no Accessibility permission): just leave the text on the clipboard."""
    pb = NSPasteboard.generalPasteboard()
    if not can_type:
        put_private(pb, text)
        return
    previous = pb.stringForType_(NSPasteboardTypeString)
    put_private(pb, text)
    time.sleep(0.03)
    _cmd_v()
    time.sleep(0.4)  # let the target app read the clipboard before restoring
    pb.clearContents()  # never leave the dictated text behind
    if previous is not None:
        pb.setString_forType_(previous, NSPasteboardTypeString)
