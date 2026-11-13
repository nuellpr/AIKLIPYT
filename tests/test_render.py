import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.assets import ffmpeg_path  # noqa: E402
from core.render import ass_time, build_ass, probe_size, render_clip  # noqa: E402
from core.subtitles import Word  # noqa: E402

FFMPEG = ffmpeg_path()


class AssTests(unittest.TestCase):
    def test_ass_contains_hook_captions_credit(self):
        words = [Word("halo", 0.2, 0.7), Word("dunia", 0.8, 1.4)]
        ass = build_ass(words, "TONTON INI", "@kredit", 1.5, 2.0)
        self.assertIn("PlayResX: 1080", ass)
        self.assertIn("PlayResY: 1920", ass)
        self.assertIn("Style: Hook", ass)
        self.assertIn("TONTON INI", ass)
        self.assertIn("&H0000D7FF", ass)
        self.assertIn("halo", ass)
        self.assertIn("dunia", ass)
        self.assertIn("@kredit", ass)
        self.assertIn("0:00:00.00,0:00:01.50,Hook", ass)

    def test_ass_escapes_braces(self):
        ass = build_ass([], "{evil\\pos(0,0)}", "", 1, 2)
        self.assertNotIn("{evil", ass)
        self.assertIn("(EVIL", ass)

    def test_caption_color_and_styles(self):
        words = [Word("halo", 0.2, 0.7), Word("dunia", 0.8, 1.4)]
        colored = build_ass(words, caption_color="#00FF00")
        self.assertIn("&H0000FF00&", colored)
        box = build_ass(words, caption_style="box")
        self.assertIn(r"\bord10", box)
        self.assertIn(r"\3c&H0000D7FF&", box)
        pop = build_ass(words, caption_style="pop")
        self.assertIn(r"\fscx115", pop)
        fallback = build_ass(words, caption_color="nope", caption_style="nope")
        self.assertIn("&H0000D7FF&", fallback)

    def test_time_format(self):
        self.assertEqual(ass_time(0), "0:00:00.00")
        self.assertEqual(ass_time(62.5), "0:01:02.50")
        self.assertEqual(ass_time(3661.25), "1:01:01.25")


@unittest.skipUnless(FFMPEG, "ffmpeg not available")
class FfmpegRenderTests(unittest.TestCase):
    def test_portrait_render(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            source = work / "input.mp4"
            subprocess.run(
                [
                    FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=2",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(source),
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )
            output = work / "out" / "clip_01.mp4"
            words = [Word("halo", 0.2, 0.7), Word("dunia", 0.8, 1.4)]
            render_clip(
                source,
                output,
                words,
                FFMPEG,
                2.0,
                hook_text="TONTON INI",
                credit="@test",
                hook_seconds=1.0,
            )
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 1000)
            self.assertEqual(probe_size(output, FFMPEG), (1080, 1920))


if __name__ == "__main__":
    unittest.main()
