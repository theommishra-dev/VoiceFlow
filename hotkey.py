"""Push-to-talk on right Option, via a listen-only Quartz event tap.

on_press()  : right Option went down on its own
on_release(): right Option came up -> stop and transcribe
on_cancel() : another key was pressed while holding it (an Option shortcut
              like Option+E), so the recording is thrown away
"""
import Quartz

RIGHT_OPTION_KEYCODE = 61
NX_DEVICERALTKEYMASK = 0x00000040  # device-dependent bit for the right Option key


class RightOptionHotkey:
    def __init__(self, on_press, on_release, on_cancel):
        self.on_press, self.on_release, self.on_cancel = on_press, on_release, on_cancel
        self.held = False
        self.cancelled = False
        self._tap = self._source = None

    def _callback(self, proxy, etype, event, refcon):
        if etype in (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput):
            Quartz.CGEventTapEnable(self._tap, True)
            return event
        if etype == Quartz.kCGEventFlagsChanged:
            code = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
            flags = Quartz.CGEventGetFlags(event)
            if code == RIGHT_OPTION_KEYCODE:
                down = bool(flags & NX_DEVICERALTKEYMASK)
                if down and not self.held:
                    self.held, self.cancelled = True, False
                    self.on_press()
                elif not down and self.held:
                    self.held = False
                    if not self.cancelled:
                        self.on_release()
            elif self.held and not self.cancelled:
                # Another modifier joined (e.g. right Option + Shift): treat as a shortcut.
                self.cancelled = True
                self.on_cancel()
        elif etype == Quartz.kCGEventKeyDown and self.held and not self.cancelled:
            self.cancelled = True
            self.on_cancel()
        return event

    def stop(self):
        if self._tap is not None:
            Quartz.CGEventTapEnable(self._tap, False)
            Quartz.CFRunLoopRemoveSource(Quartz.CFRunLoopGetMain(), self._source, Quartz.kCFRunLoopCommonModes)
            Quartz.CFMachPortInvalidate(self._tap)
            self._tap = self._source = None
        self.held = False

    def start(self) -> bool:
        """Install the tap on the main run loop. False = permission missing."""
        mask = Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged) | Quartz.CGEventMaskBit(
            Quartz.kCGEventKeyDown
        )
        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            mask,
            self._callback,
            None,
        )
        if self._tap is None:
            return False
        self._source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        Quartz.CFRunLoopAddSource(Quartz.CFRunLoopGetMain(), self._source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(self._tap, True)
        return True
