import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ytdlp import YtdlpError, _clock, download_section, pick_subtitle  # noqa: E402


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

    def test_auto_uses_video_metadata_language_before_alphabetical_fallback(self):
        info = {
            "language": "id",
            "subtitles": {},
            "automatic_captions": {"af": [{}], "ar": [{}], "en": [{}], "id": [{}]},
        }
        self.assertEqual(pick_subtitle(info, "auto"), {"kind": "auto", "code": "id"})

    def test_auto_without_metadata_prefers_english_auto_over_afrikaans(self):
        info = {
            "subtitles": {},
            "automatic_captions": {"af": [{}], "ar": [{}], "en": [{}]},
        }
        self.assertEqual(pick_subtitle(info, "auto"), {"kind": "auto", "code": "en"})


class DownloadSectionTimeoutTests(unittest.TestCase):
    def test_timeout_kills_process_tree(self):
        import os
        import subprocess
        import tempfile
        from io import BytesIO
        from unittest import mock

        class HangingProc:
            pid = 42424
            returncode = None

            def __init__(self):
                self.stdout = BytesIO(b"")
                self.killed = False

            def wait(self, timeout=None):
                raise subprocess.TimeoutExpired("yt-dlp", timeout)

            def kill(self):
                self.killed = True

        proc = HangingProc()
        with tempfile.TemporaryDirectory() as folder:
            with (
                mock.patch("core.ytdlp.ffmpeg_path", return_value=""),
                mock.patch("core.ytdlp.deno_path", return_value=""),
                mock.patch("core.ytdlp.subprocess.Popen", return_value=proc),
                mock.patch("core.ytdlp.subprocess.run") as mock_run,
            ):
                with self.assertRaises(YtdlpError):
                    download_section("https://www.youtube.com/watch?v=dQw4w9WgXcQ", 0, 10, None, Path(folder), timeout=5)
        if os.name == "nt":
            mock_run.assert_called()
            cmd = mock_run.call_args[0][0]
            self.assertEqual(cmd[:4], ["taskkill", "/F", "/T", "/PID"])
        else:
            self.assertTrue(proc.killed)

    def test_download_section_uses_high_res_format_when_requested(self):
        import tempfile
        from io import BytesIO
        from unittest import mock

        class GoodProc:
            pid = 12345
            returncode = 0

            def __init__(self):
                self.stdout = BytesIO(b"[download] 100.0%\n")

            def wait(self, timeout=None):
                return 0

            def kill(self):
                pass

        with tempfile.TemporaryDirectory() as folder:
            out_dir = Path(folder)
            (out_dir / "section.mp4").write_bytes(b"mp4")
            seen_cmds = []

            def fake_popen(cmd, **kwargs):
                seen_cmds.append(cmd)
                return GoodProc()

            with (
                mock.patch("core.ytdlp.ffmpeg_path", return_value=""),
                mock.patch("core.ytdlp.deno_path", return_value=""),
                mock.patch("core.ytdlp.subprocess.Popen", side_effect=fake_popen),
            ):
                download_section("https://www.youtube.com/watch?v=dQw4w9WgXcQ", 0, 10, None, out_dir)
                download_section("https://www.youtube.com/watch?v=dQw4w9WgXcQ", 0, 10, None, out_dir, max_height=2160)

        fmt_default = seen_cmds[0][seen_cmds[0].index("-f") + 1]
        fmt_hi = seen_cmds[1][seen_cmds[1].index("-f") + 1]
        self.assertNotIn("--force-keyframes-at-cuts", seen_cmds[0])
        self.assertIn("height<=1080", fmt_default)
        self.assertNotIn("height<=2160", fmt_default)
        self.assertIn("height<=2160", fmt_hi)
        self.assertIn("bv*[height<=2160]+ba", fmt_hi)

    def test_base_resolves_relative_cookie_path(self):
        import os
        import tempfile
        from unittest import mock
        from core.ytdlp import _base

        with tempfile.TemporaryDirectory() as folder:
            cookie = Path(folder) / "cookies.txt"
            cookie.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
            prev = Path.cwd()
            try:
                os.chdir(folder)
                with (
                    mock.patch("core.ytdlp.ffmpeg_path", return_value=""),
                    mock.patch("core.ytdlp.deno_path", return_value=""),
                ):
                    cmd = _base("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "cookies.txt")
            finally:
                os.chdir(prev)
        idx = cmd.index("--cookies")
        self.assertEqual(Path(cmd[idx + 1]), cookie.resolve())
        self.assertTrue(Path(cmd[idx + 1]).is_absolute())


if __name__ == "__main__":
    unittest.main()
