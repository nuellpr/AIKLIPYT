import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.pipeline import _bilingual_translations  # noqa: E402
from core.subtitles import Word  # noqa: E402


class BilingualTranslationTests(unittest.TestCase):
    def test_builds_one_line_per_group_in_order(self):
        words = [Word("a", 0.1, 0.4), Word("b", 0.5, 0.8), Word("c", 3.0, 3.4)]
        seen = {}

        def fake(texts, target, base, key, model):
            seen["texts"] = texts
            return [f"T{i}" for i in range(len(texts))]

        out = _bilingual_translations(words, "Indonesian", "base", "key", "model", translate=fake)
        self.assertEqual(seen["texts"], ["a b", "c"])
        self.assertEqual(out, ["T0", "T1"])

    def test_ai_failure_returns_none(self):
        def boom(*a, **k):
            raise RuntimeError("offline")

        self.assertIsNone(
            _bilingual_translations([Word("a", 0.1, 0.4)], "id", "b", "k", "m", translate=boom)
        )


if __name__ == "__main__":
    unittest.main()
