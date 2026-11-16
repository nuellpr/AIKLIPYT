import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ytdlp import _clock  # noqa: E402


class ClockTests(unittest.TestCase):
    def test_formats_seconds(self):
        self.assertEqual(_clock(0), "00:00:00.000")
        self.assertEqual(_clock(62.5), "00:01:02.500")
        self.assertEqual(_clock(3661.25), "01:01:01.250")

    def test_rounding_carries_instead_of_reaching_60(self):
        self.assertEqual(_clock(59.9999), "00:01:00.000")


if __name__ == "__main__":
    unittest.main()
