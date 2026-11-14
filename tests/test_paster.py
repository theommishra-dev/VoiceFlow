"""Privacy checks for the clipboard step. Uses a private, uniquely named pasteboard,
never your real clipboard. Run:  ./.venv/bin/python -m unittest discover tests
"""
import sys
import unittest
from pathlib import Path

from AppKit import NSPasteboard, NSPasteboardTypeString
from Foundation import NSData

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import paster  # noqa: E402


class PasterPrivacyTest(unittest.TestCase):
    def test_text_is_marked_so_clipboard_managers_skip_it(self):
        pb = NSPasteboard.pasteboardWithUniqueName()
        try:
            paster.put_private(pb, "secret dictation")
            self.assertEqual(pb.stringForType_(NSPasteboardTypeString), "secret dictation")
            types = set(pb.types())
            self.assertIn("org.nspasteboard.TransientType", types)
            self.assertIn("org.nspasteboard.ConcealedType", types)
        finally:
            pb.releaseGlobally()

    def test_shared_copy_stays_and_is_hidden_from_clipboard_managers(self):
        pb = NSPasteboard.pasteboardWithUniqueName()
        try:
            paster.paste("for my iPhone", can_type=False, share=True, pb=pb)
            self.assertEqual(pb.stringForType_(NSPasteboardTypeString), "for my iPhone")
            types = set(pb.types())
            self.assertIn("org.nspasteboard.ConcealedType", types)
            self.assertNotIn("org.nspasteboard.TransientType", types)  # it stays, so not transient
        finally:
            pb.releaseGlobally()

    def test_this_mac_only_mode_is_marked_transient(self):
        pb = NSPasteboard.pasteboardWithUniqueName()
        try:
            paster.paste("just this Mac", can_type=False, pb=pb)
            self.assertIn("org.nspasteboard.TransientType", set(pb.types()))
        finally:
            pb.releaseGlobally()

    def test_old_clipboard_comes_back_even_when_it_is_not_text(self):
        """A copied image or file must survive a dictation (it used to be wiped)."""
        pb = NSPasteboard.pasteboardWithUniqueName()
        try:
            png = NSData.dataWithBytes_length_(b"\x89PNG fake image bytes", 21)
            pb.clearContents()
            pb.setData_forType_(png, "public.png")
            pb.setString_forType_("caption", NSPasteboardTypeString)
            saved = paster.snapshot(pb)
            paster.put_private(pb, "dictated words")
            paster.restore(pb, saved)
            self.assertEqual(bytes(pb.dataForType_("public.png")), b"\x89PNG fake image bytes")
            self.assertEqual(pb.stringForType_(NSPasteboardTypeString), "caption")
            self.assertNotIn("org.nspasteboard.TransientType", set(pb.types()))
        finally:
            pb.releaseGlobally()

    def test_empty_clipboard_stays_empty_after_dictation(self):
        pb = NSPasteboard.pasteboardWithUniqueName()
        try:
            pb.clearContents()
            saved = paster.snapshot(pb)
            paster.put_private(pb, "dictated words")
            paster.restore(pb, saved)
            self.assertIsNone(pb.stringForType_(NSPasteboardTypeString))
        finally:
            pb.releaseGlobally()


if __name__ == "__main__":
    unittest.main()
