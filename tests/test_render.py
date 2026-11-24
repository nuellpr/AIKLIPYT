import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.assets import ffmpeg_path  # noqa: E402
from core.render import (  # noqa: E402
    BACKGROUND_MODES,
    CAPTION_FONTS,
    CAPTION_STYLES,
    FACECAM_CORNERS,
    HOOK_STYLES,
    MRBEAST_COLORS,
    _filter_complex,
    _portrait_chain,
    ass_time,
    build_ass,
    probe_size,
    render_clip,
)
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
        self.assertIn(",CaptionBg,", box)
        self.assertIn(r"{\rCaptionBg}", box)
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
        line = next(row for row in ass.splitlines() if row.startswith("Dialogue:"))
        self.assertLess(line.index(r"\bord12"), line.index("HALO"))

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
        words = [
            Word(tok, i * 0.4 + 0.1, i * 0.4 + 0.35)
            for i, tok in enumerate(("a", "b", "c", "d", "e", "f"))
        ]
        ass = build_ass(words, caption_style="mrbeast")
        dialogues = [row for row in ass.splitlines() if row.startswith("Dialogue:")]
        first_line = dialogues[0]
        self.assertIn(r"\fscx120", first_line)
        self.assertLess(first_line.index(r"\bord8\3c&HFFFFFF&"), first_line.index("}A"))
        self.assertIn(r"{\bord8\3c&H000000&\shad2}B", first_line)
        self.assertIn("&H000000FF&", MRBEAST_COLORS)
        joined = "\n".join(dialogues)
        for color in MRBEAST_COLORS:
            self.assertIn(color, joined)

    def test_adjacent_groups_never_overlap(self):
        # 5 words split into 2 groups; group 1's last word has a bloated rolling end time.
        words = [
            Word("one", 0.0, 0.3),
            Word("two", 0.3, 0.6),
            Word("three", 0.6, 0.9),
            Word("four", 0.9, 4.5),
            Word("five", 1.2, 1.5),
        ]
        for style in ("highlight", "karaoke", "bilingual"):
            ass = build_ass(words, caption_style=style, translations=["satu", "dua"])
            by_style: dict[str, list[tuple[str, str]]] = {}
            for line in ass.splitlines():
                if not line.startswith("Dialogue:"):
                    continue
                parts = line.split(",", 9)
                by_style.setdefault(parts[3], []).append((parts[1], parts[2]))
            for style_name, times in by_style.items():
                for (_, prev_end), (next_start, _) in zip(times, times[1:]):
                    self.assertLessEqual(prev_end, next_start, f"{style}/{style_name}: {prev_end} > {next_start}")

    def test_same_start_words_never_overlap_in_ass(self):
        words = [
            Word("pikir", 1.0, 1.2),
            Word("sana", 1.0, 1.2),
            Word("kan", 1.5, 1.6),
            Word("itu", 1.5, 1.65),
            Word("lagi", 1.7, 1.9),
        ]
        for style in ("highlight", "box-highlight"):
            ass = build_ass(words, caption_style=style)
            times = [
                (line.split(",", 9)[1], line.split(",", 9)[2])
                for line in ass.splitlines()
                if line.startswith("Dialogue:")
            ]
            for (_, prev_end), (next_start, _) in zip(times, times[1:]):
                self.assertLessEqual(prev_end, next_start, f"{style}: {prev_end} > {next_start}")

    def test_render_clip_preserves_existing_file_on_failure(self):
        from io import BytesIO
        from unittest import mock

        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            src = work / "in.mp4"
            src.write_bytes(b"in")
            out = work / "clip_01.mp4"
            out.write_bytes(b"existing-good-mp4" * 100)

            class BadProc:
                returncode = 1

                def __init__(self):
                    self.stdout = BytesIO(b"")

                def wait(self, timeout=None):
                    return 1

                def kill(self):
                    pass

            with (
                mock.patch("core.render.detect_encoder", return_value=None),
                mock.patch("core.render.subprocess.Popen", return_value=BadProc()),
            ):
                with self.assertRaises(RuntimeError):
                    render_clip(src, out, [], "ffmpeg", 2.0)

            self.assertEqual(out.read_bytes(), b"existing-good-mp4" * 100)
            self.assertFalse((work / ".clip_01.tmp.mp4").exists())

    def test_caption_font_and_bold(self):
        words = [Word("halo", 0.2, 0.7)]
        regular = build_ass(words, caption_font="Segoe UI", caption_bold=False)
        self.assertIn("Style: Caption,Segoe UI,62,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,", regular)
        self.assertIn("Style: CaptionBg,Segoe UI,62,&H00FFFFFF,&H000000FF,&H00031410,&H80000000,0,", regular)
        self.assertIn("Style: CaptionAlt,Segoe UI,46,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,", regular)
        bold = build_ass(words, caption_font="Georgia", caption_bold=True)
        self.assertIn("Style: Caption,Georgia,62,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,", bold)
        gadzhi_custom = build_ass(words, caption_style="gadzhi", caption_font="Georgia")
        self.assertIn(r"\fnGeorgia\b0", gadzhi_custom)
        injected = build_ass(words, caption_font="Arial,99\nStyle: Evil")
        self.assertIn("Style: Caption,Arial Black,", injected)
        self.assertNotIn("Style: Evil", injected)
        self.assertGreaterEqual(len(CAPTION_FONTS), 10)

    def test_filter_complex_uses_custom_ass_file(self):
        graph = _filter_complex(True, "black", True, None, 0.9, ass_file="clip_02.ass")
        self.assertIn(",ass=clip_02.ass", graph)

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

    def test_hook_styles(self):
        words = [Word("halo", 0.2, 0.7)]
        self.assertEqual(len(HOOK_STYLES), 11)
        card = build_ass(words, hook_text="Ternyata dia", hook_style="card")
        self.assertIn(",HookBox,,", card)
        self.assertIn("Ternyata dia", card)
        quote = build_ass(words, hook_text="Ternyata dia", hook_style="quote")
        self.assertIn("“ ", quote)
        bar = build_ass(words, hook_text="Ternyata dia", hook_style="accent-bar")
        self.assertIn("TERNYATA DIA", bar)
        cinema = build_ass(words, hook_text="Ternyata dia", hook_style="cinema")
        self.assertIn(r"\fsp6", cinema)
        neon = build_ass(words, hook_text="Ternyata dia", hook_style="neon")
        self.assertIn(r"\blur10", neon)
        breaking = build_ass(words, hook_text="Ternyata dia", hook_style="breaking")
        self.assertIn("● TERNYATA DIA", breaking)
        impact = build_ass(words, hook_text="Ternyata dia", hook_style="impact")
        self.assertIn(r"\t(0,180,\fscx100\fscy100)", impact)
        tape = build_ass(words, hook_text="Ternyata dia", hook_style="tape")
        self.assertIn(r"\frz3", tape)
        spot = build_ass(words, hook_text="Ternyata dia nolak satu miliar", hook_style="spotlight")
        self.assertIn(r"\i1", spot)
        self.assertIn("TERNYATA DIA", spot)
        self.assertIn("NOLAK SATU MILIAR", spot)
        retro = build_ass(
            [Word("awal", 0.2, 0.7), Word("akhir", 3.5, 4.0)],
            hook_text="Inilah satu-satunya kelebihan dia yg luar biasa",
            hook_style="retro-card",
            hook_seconds=3.0,
        )
        self.assertIn(r"\p1", retro)
        self.assertIn("&H0069E1FF&", retro)
        layer3 = [r for r in retro.splitlines() if r.startswith("Dialogue: 3,")]
        self.assertGreater(len(layer3), 3)
        self.assertIn(",Caption,,0,0,600,,", retro)
        self.assertIn(",Caption,,0,0,0,,", retro)
        fallback = build_ass(words, hook_text="Halo", hook_style="unknown")
        self.assertIn(",Hook,,0,0,0,,HALO", fallback)

    def test_fill_portrait_chain(self):
        chain = _portrait_chain("fill")
        self.assertEqual(
            chain,
            "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,unsharp=3:3:0.5:3:3:0.0",
        )

    def test_background_modes_and_portrait_chains(self):
        self.assertEqual(len(BACKGROUND_MODES), 8)
        self.assertEqual(len(FACECAM_CORNERS), 4)
        for mode in BACKGROUND_MODES:
            chain = _portrait_chain(mode)
            self.assertTrue(chain, mode)
        self.assertIn("(iw-ow)*0.15", _portrait_chain("crop-left"))
        self.assertIn("(iw-ow)*0.85", _portrait_chain("crop-right"))
        self.assertIn("vstack=inputs=2", _portrait_chain("split"))
        self.assertIn("1080:1350", _portrait_chain("cinema"))
        self.assertIn("color=black", _portrait_chain("unknown"))
        fc_tl = _portrait_chain("facecam-top", "top-left")
        fc_br = _portrait_chain("facecam-top", "bottom-right")
        self.assertIn(":0:0,", fc_tl)
        self.assertIn(":iw-ow:ih-oh,", fc_br)
        self.assertIn("vstack=inputs=2", fc_tl)

    def test_filter_complex_split_and_facecam_with_overlays(self):
        for mode in ("split", "facecam-top", "cinema"):
            graph = _filter_complex(
                True,
                mode,
                True,
                Path("logo.png"),
                0.75,
                "bottom-right",
                ass_file="clip_01.ass",
                facecam_corner="bottom-left",
            )
            self.assertIn(",ass=clip_01.ass[base]", graph)
            self.assertIn("overlay=W-w-40:H-h-40[v]", graph)
            if mode == "facecam-top":
                self.assertIn(":0:ih-oh,", graph)

    def test_caption_uppercase_and_bold_variants(self):
        words = [Word("halo", 0.2, 0.7), Word("dunia", 0.8, 1.4)]
        upper_reg = build_ass(words, caption_style="highlight", caption_font="Segoe UI", caption_bold=False, caption_uppercase=True)
        self.assertIn("Style: Caption,Segoe UI,62,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,", upper_reg)
        self.assertIn("HALO", upper_reg)
        self.assertIn("DUNIA", upper_reg)

        upper_bold = build_ass(words, caption_style="box-highlight", caption_font="Segoe UI", caption_bold=True, caption_uppercase=True)
        self.assertIn("Style: Caption,Segoe UI,62,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,", upper_bold)
        self.assertIn("HALO", upper_bold)

        kara = build_ass(words, caption_style="karaoke", caption_uppercase=True)
        self.assertIn("HALO", kara)
        bi = build_ass(words, caption_style="bilingual", translations=["hello world"], caption_uppercase=True)
        self.assertIn("HELLO WORLD", bi)

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
            self.assertTrue((work / "out" / "clip_01.ass").is_file())
            self.assertFalse((work / "out" / "captions.ass").exists())
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
            for idx, style in enumerate((
                "smart-bg-focus", "box-highlight", "word-focus", "underline-focus", "outline-focus", "temp-0",
                "hormozi", "karaoke", "gadzhi", "mrbeast", "bilingual",
            )):
                output = work / f"out_{style}.mp4"
                render_clip(
                    source,
                    output,
                    words,
                    FFMPEG,
                    1.5,
                    hook_text="Ternyata dia nolak 1 miliar" if idx < len(HOOK_STYLES) else "",
                    hook_style=HOOK_STYLES[idx] if idx < len(HOOK_STYLES) else "classic",
                    portrait=False,
                    caption_style=style,
                    caption_font="Segoe UI" if style == "highlight" else "Arial Black",
                    caption_bold=False if style == "bilingual" else True,
                )
                self.assertTrue(output.is_file(), style)
                self.assertGreater(output.stat().st_size, 1000, style)
            custom_out = work / "out_custom_font.mp4"
            render_clip(
                source,
                custom_out,
                words,
                FFMPEG,
                1.5,
                portrait=False,
                caption_font="Segoe UI",
                caption_bold=False,
            )
            self.assertTrue(custom_out.is_file())
            self.assertGreater(custom_out.stat().st_size, 1000)

            rel_logo = Path("web/assets/logo.png")
            if rel_logo.is_file():
                logo_out = work / "out_rel_logo.mp4"
                render_clip(
                    source,
                    logo_out,
                    words,
                    FFMPEG,
                    1.5,
                    portrait=False,
                    watermark=str(rel_logo),
                )
                self.assertTrue(logo_out.is_file())
                self.assertGreater(logo_out.stat().st_size, 1000)

    def test_fill_retro_card_uppercase_render(self):
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
            output = work / "out_fill_retro.mp4"
            words = [Word("satu", 0.2, 0.7), Word("doang", 0.8, 1.4)]
            render_clip(
                source,
                output,
                words,
                FFMPEG,
                2.0,
                hook_text="inilah satu-satunya kelebihan dia yg luar biasa",
                hook_style="retro-card",
                hook_seconds=1.5,
                portrait=True,
                background="fill",
                caption_font="Segoe UI",
                caption_bold=False,
                caption_uppercase=True,
            )
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 1000)
            self.assertEqual(probe_size(output, FFMPEG), (1080, 1920))

    def test_new_framing_modes_render(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            source = work / "input.mp4"
            subprocess.run(
                [
                    FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=1",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(source),
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )
            logo = Path("web/assets/logo.png")
            words = [Word("halo", 0.1, 0.5), Word("dunia", 0.5, 0.9)]
            for mode in ("split", "crop-left", "crop-right", "facecam-top", "cinema"):
                output = work / f"out_{mode}.mp4"
                render_clip(
                    source,
                    output,
                    words,
                    FFMPEG,
                    1.0,
                    hook_text="TES MODE",
                    portrait=True,
                    background=mode,
                    facecam_corner="bottom-left" if mode == "facecam-top" else "top-right",
                    watermark=str(logo) if mode == "facecam-top" and logo.is_file() else "",
                )
                self.assertTrue(output.is_file(), mode)
                self.assertGreater(output.stat().st_size, 1000, mode)
                self.assertEqual(probe_size(output, FFMPEG), (1080, 1920), mode)


if __name__ == "__main__":
    unittest.main()
