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


if __name__ == "__main__":
    unittest.main()
