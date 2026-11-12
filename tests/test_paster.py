"""Privacy checks for the clipboard step. Uses a private, uniquely named pasteboard,
never your real clipboard. Run:  ./.venv/bin/python -m unittest discover tests
"""
import sys
import unittest
from pathlib import Path

from AppKit import NSPasteboard, NSPasteboardTypeString

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

    def test_private_mode_is_the_default(self):
        pb = NSPasteboard.pasteboardWithUniqueName()
        try:
            paster.paste("just this Mac", can_type=False, pb=pb)
            self.assertIn("org.nspasteboard.TransientType", set(pb.types()))
        finally:
            pb.releaseGlobally()


if __name__ == "__main__":
    unittest.main()
