import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.assets import ffmpeg_path  # noqa: E402
from core.render import CAPTION_STYLES, _filter_complex, ass_time, build_ass, probe_size, render_clip  # noqa: E402
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

    def test_credit_and_logo_positions(self):
        words = [Word("halo", 0.2, 0.7)]
        top = build_ass(words, credit="@kredit", duration=2, credit_position="top-left")
        center = build_ass(words, credit="@kredit", duration=2, credit_position="center")
        self.assertIn(r"{\an7\pos(60,60)}@kredit", top)
        self.assertIn(r"{\an5\pos(540,960)}@kredit", center)
        graph = _filter_complex(True, "black", False, Path("logo.png"), 0.9, "bottom-left")
        self.assertIn("overlay=40:H-h-40", graph)

    def test_branding_opacity(self):
        ass = build_ass([Word("halo", 0.2, 0.7)], credit="@kredit", duration=2, credit_opacity=0.5)
        self.assertIn(r"\alpha&H80&", ass)
        graph = _filter_complex(True, "black", False, Path("logo.png"), 0.4, "top-right")
        self.assertIn("colorchannelmixer=aa=0.40", graph)

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

    def test_wayin_caption_styles(self):
        words = [Word("halo", 0.2, 0.7), Word("dunia", 0.8, 1.4)]
        smart = build_ass(words, caption_style="smart-bg-focus")
        self.assertIn("Style: CaptionBg", smart)
        self.assertIn(",CaptionBg,", smart)
        self.assertIn("&H0000D7FF&", smart)
        box = build_ass(words, caption_style="box-highlight")
        self.assertIn(r"\bord14", box)
        self.assertNotIn("halo dunia", box)
        focus = build_ass(words, caption_style="word-focus")
        self.assertIn(r"\alpha&H80&", focus)
        self.assertIn(r"\fscx110", focus)
        underline = build_ass(words, caption_style="underline-focus")
        self.assertIn(r"\u1", underline)
        self.assertIn("HALO", underline)
        outline = build_ass(words, caption_style="outline-focus")
        self.assertIn(r"\1a&HFF&", outline)
        self.assertIn(r"\bord3", outline)
        temp0 = build_ass(words, caption_style="temp-0")
        self.assertIn("HALO", temp0)
        self.assertIn("DUNIA", temp0)
        self.assertIn(r"\shad0", temp0)
        self.assertIn(r"\3c&H000000&", temp0)

    def test_caption_styles_exposes_new_presets(self):
        for name in ("hormozi", "karaoke", "gadzhi", "mrbeast", "bilingual"):
            self.assertIn(name, CAPTION_STYLES)
        self.assertEqual(len(CAPTION_STYLES), 14)

    def test_hormozi_style(self):
        ass = build_ass([Word("halo", 0.2, 0.7)], caption_style="hormozi")
        self.assertIn(r"\bord12", ass)
        self.assertIn("HALO", ass)

    def test_karaoke_style(self):
        words = [Word("halo", 0.2, 0.7), Word("dunia", 0.8, 1.4)]
        ass = build_ass(words, caption_style="karaoke")
        self.assertIn(r"{\kf", ass)
        self.assertIn(r"\2c&H00FFFFFF&", ass)

    def test_karaoke_single_word_min_duration(self):
        # A zero-length word must still produce a positive karaoke fill time.
        ass = build_ass([Word("halo", 0.2, 0.2)], caption_style="karaoke")
        self.assertIn(r"{\kf1}", ass)

    def test_gadzhi_style(self):
        ass = build_ass([Word("halo", 0.2, 0.7)], caption_style="gadzhi")
        self.assertIn(r"\fnArial\b0", ass)
        self.assertIn(r"\bord1", ass)

    def test_mrbeast_style(self):
        words = [Word("a", 0.1, 0.4), Word("b", 0.5, 0.8), Word("c", 0.9, 1.2)]
        ass = build_ass(words, caption_style="mrbeast")
        self.assertIn(r"\fscx120", ass)
        self.assertIn("A", ass)

    def test_bilingual_renders_translation_above(self):
        words = [Word("halo", 0.2, 0.7)]
        ass = build_ass(words, "TONTON INI", "@kredit", 1.5, 2.0,
                        caption_style="bilingual", translations=["Halo!"])
        self.assertIn("halo", ass)
        self.assertIn("Halo!", ass)
        self.assertIn("CaptionAlt", ass)

    def test_bilingual_translation_is_once_per_group(self):
        # Two close words form one group; the translation must appear once, not once per word.
        words = [Word("halo", 0.2, 0.7), Word("dunia", 0.8, 1.4)]
        ass = build_ass(words, caption_style="bilingual", translations=["Halo dunia!"])
        alt_events = [line for line in ass.splitlines()
                      if line.startswith("Dialogue:") and "CaptionAlt" in line]
        self.assertEqual(len(alt_events), 1)

    def test_bilingual_partial_translations(self):
        # 5 words become 2 groups; only the first gets a translation. The short
        # translations list must not crash and every original word still renders.
        words = [Word("a", 0.1, 0.4), Word("b", 0.5, 0.8), Word("c", 0.9, 1.2),
                 Word("d", 1.3, 1.6), Word("e", 1.7, 2.0)]
        ass = build_ass(words, caption_style="bilingual", translations=["only"])
        for token in ("a", "b", "c", "d", "e"):
            self.assertIn(token, ass)
        self.assertIn("only", ass)

    def test_bilingual_escapes_translation(self):
        words = [Word("halo", 0.2, 0.7)]
        ass = build_ass(words, caption_style="bilingual", translations=["{evil\\pos(0,0)}"])
        self.assertNotIn("{evil", ass)

    def test_time_format(self):
        self.assertEqual(ass_time(0), "0:00:00.00")
        self.assertEqual(ass_time(62.5), "0:01:02.50")
        self.assertEqual(ass_time(3661.25), "1:01:01.25")
        self.assertEqual(ass_time(59.999), "0:01:00.00")


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

    def test_wayin_styles_render(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            source = work / "input.mp4"
            subprocess.run(
                [
                    FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=1.5",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1.5",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(source),
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )
            words = [Word("halo", 0.2, 0.7), Word("dunia", 0.8, 1.4)]
            for style in ("smart-bg-focus", "box-highlight", "word-focus", "underline-focus", "outline-focus", "temp-0",
                          "hormozi", "karaoke", "gadzhi", "mrbeast", "bilingual"):
                output = work / f"out_{style}.mp4"
                render_clip(
                    source,
                    output,
                    words,
                    FFMPEG,
                    1.5,
                    portrait=False,
                    caption_style=style,
                )
                self.assertTrue(output.is_file(), style)
                self.assertGreater(output.stat().st_size, 1000, style)


if __name__ == "__main__":
    unittest.main()
