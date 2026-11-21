import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ytdlp import _clock, pick_subtitle  # noqa: E402


class ClockTests(unittest.TestCase):
    def test_formats_seconds(self):
        self.assertEqual(_clock(0), "00:00:00.000")
        self.assertEqual(_clock(62.5), "00:01:02.500")
        self.assertEqual(_clock(3661.25), "01:01:01.250")

    def test_rounding_carries_instead_of_reaching_60(self):
        self.assertEqual(_clock(59.9999), "00:01:00.000")


class PickSubtitleTests(unittest.TestCase):
    def test_prefers_regional_manual_over_auto_translation(self):
        info = {
            "subtitles": {"en-US": [{}]},
            "automatic_captions": {"id-orig": [{}], "en": [{}]},
        }
        self.assertEqual(pick_subtitle(info, "en"), {"kind": "manual", "code": "en-US"})

    def test_auto_language_normalizes_to_original(self):
        info = {
            "subtitles": {"en-US": [{}]},
            "automatic_captions": {"id-orig": [{}]},
        }
        self.assertEqual(pick_subtitle(info, "auto"), {"kind": "auto", "code": "id-orig"})

    def test_fallback_matches_regional_english_manual(self):
        info = {"subtitles": {"fr": [{}], "en-GB": [{}]}, "automatic_captions": {}}
        self.assertEqual(pick_subtitle(info, ""), {"kind": "manual", "code": "en-GB"})


if __name__ == "__main__":
    unittest.main()
