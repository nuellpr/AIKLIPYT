import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.subtitles import (  # noqa: E402
    Word,
    parse_json3,
    parse_srt,
    parse_timestamp,
    parse_vtt,
    slice_words,
    transcript,
    words_from_cues,
)


class TimestampTests(unittest.TestCase):
    def test_formats(self):
        self.assertAlmostEqual(parse_timestamp("90"), 90)
        self.assertAlmostEqual(parse_timestamp("1:02"), 62)
        self.assertAlmostEqual(parse_timestamp("01:02:03,500"), 3723.5)
        self.assertAlmostEqual(parse_timestamp("0:12.250"), 12.25)
        self.assertIsNone(parse_timestamp("nope"))

    def test_srt(self):
        srt = """1
00:00:01,000 --> 00:00:03,000
Halo <i>dunia</i>

2
00:00:04,000 --> 00:00:06,500
Baris kedua
"""
        cues = parse_srt(srt)
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0].text, "Halo dunia")
        self.assertAlmostEqual(cues[1].end, 6.5)

    def test_json3_word_timing(self):
        data = {
            "events": [
                {"tStartMs": 1000, "dDurationMs": 900, "segs": [{"utf8": "hello", "tOffsetMs": 0}, {"utf8": "world", "tOffsetMs": 400}]},
                {"tStartMs": 1900, "dDurationMs": 600, "segs": [{"utf8": "hello", "tOffsetMs": 0}, {"utf8": "again", "tOffsetMs": 300}]},
            ]
        }
        words = parse_json3(data)
        self.assertEqual([w.word for w in words], ["hello", "world", "hello", "again"])
        self.assertAlmostEqual(words[0].start, 1.0)
        self.assertAlmostEqual(words[1].start, 1.4)
        self.assertAlmostEqual(words[-1].start, 2.2)

    def test_json3_manual_sentence_is_split(self):
        data = {
            "events": [
                {"tStartMs": 0, "dDurationMs": 2000, "segs": [{"utf8": "one two three", "tOffsetMs": 0}]},
            ]
        }
        words = parse_json3(data)
        self.assertEqual([w.word for w in words], ["one", "two", "three"])
        self.assertLess(words[0].start, words[1].start)
        self.assertLess(words[1].start, words[2].start)
        self.assertAlmostEqual(words[-1].end, 2.0)

    def test_vtt_inline_timing(self):
        vtt = """WEBVTT

00:00:01.000 --> 00:00:03.000
<00:00:01.000><c>Halo</c> <00:00:01.600><c>semua</c>
"""
        cues, words = parse_vtt(vtt)
        self.assertEqual(len(cues), 1)
        self.assertEqual([w.word for w in words], ["Halo", "semua"])
        self.assertLess(words[0].start, words[1].start)
        self.assertGreater(words[1].end, words[1].start)

    def test_words_from_cues_and_transcript(self):
        cues = parse_srt("1\n00:00:01,000 --> 00:00:04,000\nsatu dua tiga\n")
        words = words_from_cues(cues)
        self.assertEqual(len(words), 3)
        self.assertGreater(words[-1].end, words[0].start)
        text = transcript(cues, words)
        self.assertIn("[0:01]", text)
        self.assertIn("satu dua tiga", text)

    def test_slice_words(self):
        words = [Word("a", 0, 1), Word("b", 4, 6), Word("c", 9, 10)]
        sliced = slice_words(words, 3, 8)
        self.assertEqual([w.word for w in sliced], ["b"])
        self.assertAlmostEqual(sliced[0].start, 1.0)
        self.assertAlmostEqual(sliced[0].end, 3.0)


if __name__ == "__main__":
    unittest.main()
