"""Paste text into whatever app has focus: clipboard + Cmd+V, then restore clipboard."""
import time

import Quartz
from AppKit import NSPasteboard, NSPasteboardTypeString

V_KEYCODE = 9


def _cmd_v():
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    for down in (True, False):
        ev = Quartz.CGEventCreateKeyboardEvent(src, V_KEYCODE, down)
        Quartz.CGEventSetFlags(ev, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def paste(text: str, can_type: bool = True):
    """can_type=False (no Accessibility permission): just leave the text on the clipboard."""
    pb = NSPasteboard.generalPasteboard()
    if not can_type:
        pb.clearContents()
        pb.setString_forType_(text, NSPasteboardTypeString)
        return
    previous = pb.stringForType_(NSPasteboardTypeString)
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)
    time.sleep(0.03)
    _cmd_v()
    time.sleep(0.4)  # let the target app read the clipboard before restoring
    if previous is not None:
        pb.clearContents()
        pb.setString_forType_(previous, NSPasteboardTypeString)
