import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import assets  # noqa: E402


class AssetsLookupTests(unittest.TestCase):
    def test_ffmpeg_found_in_assets_ffmpeg(self):
        exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "app"
            bundled = root / "assets" / "ffmpeg" / exe
            bundled.parent.mkdir(parents=True)
            bundled.write_bytes(b"")
            with (
                mock.patch.object(assets, "ROOT", root),
                mock.patch.object(assets, "_PARENT", root.parent),
                mock.patch.object(assets, "load", return_value={"paths": {"ffmpeg": "", "deno": ""}}),
                mock.patch.dict(os.environ, {}, clear=False),
                mock.patch.object(assets.shutil, "which", return_value=None),
            ):
                os.environ.pop("AIKLIPYT_FFMPEG", None)
                self.assertEqual(assets.ffmpeg_path(), str(bundled))

    def test_ffmpeg_falls_back_to_parent_ffmpeg_folder(self):
        exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder)
            root = parent / "app"
            root.mkdir()
            legacy = parent / "ffmpeg" / exe
            legacy.parent.mkdir(parents=True)
            legacy.write_bytes(b"")
            with (
                mock.patch.object(assets, "ROOT", root),
                mock.patch.object(assets, "_PARENT", parent),
                mock.patch.object(assets, "load", return_value={"paths": {"ffmpeg": "", "deno": ""}}),
                mock.patch.dict(os.environ, {}, clear=False),
                mock.patch.object(assets.shutil, "which", return_value=None),
            ):
                os.environ.pop("AIKLIPYT_FFMPEG", None)
                self.assertEqual(assets.ffmpeg_path(), str(legacy))


if __name__ == "__main__":
    unittest.main()
