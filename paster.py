"""Paste text into whatever app has focus: clipboard + Cmd+V.

Two modes:
- private (default): the text is put on the clipboard for this Mac only (no Universal
  Clipboard / Handoff to your other devices), marked transient + concealed (the
  nspasteboard.org convention that clipboard managers such as Raycast, Alfred, Paste
  and Maccy honour by not saving it), and wiped after pasting; your old clipboard
  comes back.
- share (menu: "Also copy to iPhone / iPad"): after pasting, the text stays on the
  clipboard like a normal copy, so Universal Clipboard can hand it to your iPhone or
  iPad (Apple's encrypted device-to-device transfer, same Apple ID, Handoff on).
  Still marked concealed, so clipboard managers don't keep a history of it.
"""
import time

import Quartz
from AppKit import NSPasteboard, NSPasteboardTypeString

V_KEYCODE = 9
CURRENT_HOST_ONLY = 1  # NSPasteboardContentsCurrentHostOnly: never synced to other devices
TRANSIENT = "org.nspasteboard.TransientType"
CONCEALED = "org.nspasteboard.ConcealedType"


def _cmd_v():
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    for down in (True, False):
        ev = Quartz.CGEventCreateKeyboardEvent(src, V_KEYCODE, down)
        Quartz.CGEventSetFlags(ev, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def put_private(pb, text: str):
    """This Mac only, and flagged so clipboard managers skip it."""
    pb.prepareForNewContentsWithOptions_(CURRENT_HOST_ONLY)
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)
    for marker in (TRANSIENT, CONCEALED):
        pb.setString_forType_("", marker)


def put_shared(pb, text: str):
    """A normal copy that Universal Clipboard may sync to your iPhone/iPad.
    Concealed so clipboard managers don't save it; not transient, because it stays."""
    pb.prepareForNewContentsWithOptions_(0)
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)
    pb.setString_forType_("", CONCEALED)


def paste(text: str, can_type: bool = True, share: bool = False, pb=None):
    """can_type=False (no Accessibility permission): just leave the text on the clipboard."""
    pb = pb or NSPasteboard.generalPasteboard()
    previous = None if share or not can_type else pb.stringForType_(NSPasteboardTypeString)
    (put_shared if share else put_private)(pb, text)
    if not can_type:
        return
    time.sleep(0.03)
    _cmd_v()
    if share:
        return  # leave it on the clipboard for your other devices
    time.sleep(0.4)  # let the target app read the clipboard before restoring
    pb.clearContents()  # never leave the dictated text behind
    if previous is not None:
        pb.setString_forType_(previous, NSPasteboardTypeString)
