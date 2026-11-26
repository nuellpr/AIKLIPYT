import builtins
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.assets import ffmpeg_path  # noqa: E402
from core.reframe import (  # noqa: E402
    _YUNET_MODEL,
    ShotPlan,
    _build_shot_ranges,
    _choose_shot_framing,
    _compute_crop_size,
    _create_detector,
    _merge_similar_shots,
    analyze_reframe,
    detect_scene_cuts,
)
from core.render import _reframe_chain, probe_size, render_clip  # noqa: E402
from core.subtitles import Word  # noqa: E402

FFMPEG = ffmpeg_path()


class ReframeUnitTests(unittest.TestCase):
    def test_compute_crop_size(self):
        self.assertEqual(_compute_crop_size(1920, 1080), (608, 1080))
        self.assertEqual(_compute_crop_size(3840, 2160), (1214, 2160))
        self.assertIsNone(_compute_crop_size(1080, 1920))
        self.assertIsNone(_compute_crop_size(0, 1080))

    def test_build_shot_ranges_filters_caps_and_spans(self):
        ranges = _build_shot_ranges([0.2, 1.5, 1.7, 4.0, 9.7], duration=10.0, min_shot=0.6, max_shots=30)
        self.assertEqual(ranges, [(0.0, 1.5), (1.5, 4.0), (4.0, 10.0)])

        capped = _build_shot_ranges([float(i) for i in range(1, 50)], duration=60.0, max_shots=5)
        self.assertEqual(len(capped), 5)
        self.assertEqual(capped[0][0], 0.0)
        self.assertEqual(capped[-1][1], 60.0)
        for (_, prev_end), (next_start, _) in zip(capped, capped[1:]):
            self.assertEqual(prev_end, next_start)

        self.assertEqual(_build_shot_ranges([1.0], duration=0.0), [])

    def test_choose_shot_framing_rules(self):
        # 0 faces -> center
        mode0, x0, y0 = _choose_shot_framing([], 1920, 1080, 608, 1080)
        self.assertEqual((mode0, x0, y0), ("crop", 656, 0))

        # 1 face -> locked to face with even clamped coordinates
        mode1, x1, _ = _choose_shot_framing(
            [{"cx": 320.0, "cy": 400.0, "fw": 180.0, "fh": 180.0, "count": 4, "motion": 2.0}],
            1920,
            1080,
            608,
            1080,
        )
        self.assertEqual(mode1, "crop")
        self.assertLess(x1, 100)
        self.assertEqual(x1 % 2, 0)

        # 2 close faces fitting inside 9:16 -> midpoint
        mode2, x2, _ = _choose_shot_framing(
            [
                {"cx": 820.0, "cy": 420.0, "fw": 140.0, "fh": 140.0, "count": 4, "motion": 3.0},
                {"cx": 1060.0, "cy": 420.0, "fw": 140.0, "fh": 140.0, "count": 4, "motion": 3.0},
            ],
            1920,
            1080,
            608,
            1080,
        )
        self.assertEqual(mode2, "crop")
        self.assertGreater(x2, 600)
        self.assertLess(x2, 700)

        # 2 separated faces with dominant active speaker motion -> lock onto active speaker
        mode3, x3, _ = _choose_shot_framing(
            [
                {"cx": 360.0, "cy": 420.0, "fw": 180.0, "fh": 180.0, "count": 4, "motion": 2.0},
                {"cx": 1520.0, "cy": 420.0, "fw": 180.0, "fh": 180.0, "count": 4, "motion": 9.5},
            ],
            1920,
            1080,
            608,
            1080,
        )
        self.assertEqual(mode3, "crop")
        self.assertGreater(x3, 1100)

        # 2 separated balanced speakers -> split
        mode4, _, _ = _choose_shot_framing(
            [
                {"cx": 360.0, "cy": 420.0, "fw": 180.0, "fh": 180.0, "count": 4, "motion": 2.0},
                {"cx": 1520.0, "cy": 420.0, "fw": 180.0, "fh": 180.0, "count": 4, "motion": 2.2},
            ],
            1920,
            1080,
            608,
            1080,
        )
        self.assertEqual(mode4, "split")

        # 3 speakers where 3rd slightly smaller face is the active speaker -> lock onto 3rd face
        mode5, x5, _ = _choose_shot_framing(
            [
                {"cx": 320.0, "cy": 420.0, "fw": 180.0, "fh": 180.0, "count": 4, "motion": 1.4},
                {"cx": 960.0, "cy": 420.0, "fw": 175.0, "fh": 175.0, "count": 4, "motion": 1.6},
                {"cx": 1600.0, "cy": 420.0, "fw": 160.0, "fh": 160.0, "count": 4, "motion": 10.5},
            ],
            1920,
            1080,
            608,
            1080,
        )
        self.assertEqual(mode5, "crop")
        self.assertGreater(x5, 1200)

    def test_merge_similar_shots(self):
        shots = [
            ShotPlan(0.0, 2.0, "crop", 100, 0, 608, 1080),
            ShotPlan(2.0, 4.0, "crop", 120, 0, 608, 1080),
            ShotPlan(4.0, 6.0, "crop", 1200, 0, 608, 1080),
        ]
        merged = _merge_similar_shots(shots, 1920, 1080)
        self.assertEqual(len(merged), 2)
        self.assertEqual((merged[0].start, merged[0].end, merged[0].crop_x), (0.0, 4.0, 110))
        self.assertEqual(merged[1].crop_x, 1200)

    def test_reframe_chain_shapes(self):
        one_crop = _reframe_chain([ShotPlan(0.0, 2.0, "crop", 100, 0, 608, 1080)])
        self.assertIn("crop=608:1080:100:0", one_crop)
        self.assertIn("flags=bicubic", one_crop)
        self.assertNotIn("unsharp", one_crop)

        one_split = _reframe_chain([ShotPlan(0.0, 2.0, "split", 0, 0, 608, 1080)])
        self.assertIn("vstack=inputs=2", one_split)

        mixed = _reframe_chain([
            ShotPlan(0.0, 1.0, "crop", 40, 0, 608, 1080),
            ShotPlan(1.0, 2.0, "split", 0, 0, 608, 1080),
            ShotPlan(2.0, 3.0, "crop", 1200, 0, 608, 1080),
        ])
        self.assertIn("split=3[rs0][rs1][rs2]", mixed)
        self.assertIn("trim=end=1.000", mixed)
        self.assertIn("trim=start=1.000:end=2.000", mixed)
        self.assertIn("trim=start=2.000,setpts=PTS-STARTPTS", mixed)
        self.assertIn("concat=n=3:v=1:a=0", mixed)

        crops_only = _reframe_chain([
            ShotPlan(0.0, 1.5, "crop", 40, 0, 608, 1080),
            ShotPlan(1.5, 3.0, "crop", 1200, 20, 608, 1080),
        ])
        self.assertNotIn("split=", crops_only)
        self.assertNotIn("concat=", crops_only)
        self.assertIn("lt(t,1.500)", crops_only)

    def test_analyze_reframe_falls_back_cleanly_without_cv2(self):
        real_import = builtins.__import__
        logs = []

        def no_cv2(name, *args, **kwargs):
            if name == "cv2":
                raise ImportError("missing cv2")
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=no_cv2):
            self.assertIsNone(analyze_reframe(Path("demo.mp4"), "ffmpeg", on_log=logs.append))
        self.assertTrue(any("OpenCV" in msg for msg in logs))

    def test_yunet_model_loads_and_handles_missing_path(self):
        import cv2
        import numpy as np

        self.assertTrue(_YUNET_MODEL.is_file())
        self.assertIsNone(_create_detector(cv2, 320, 180, model_path=Path("nonexistent_yunet.onnx")))
        det = _create_detector(cv2, 320, 180)
        self.assertIsNotNone(det)
        blank = np.zeros((180, 320, 3), dtype=np.uint8)
        _, faces = det.detect(blank)
        self.assertTrue(faces is None or len(faces) == 0)


@unittest.skipUnless(FFMPEG, "ffmpeg not available")
class ReframeIntegrationTests(unittest.TestCase):
    def test_scene_cuts_analyze_and_multishot_fill_render(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            source = work / "two_scenes.mp4"
            subprocess.run(
                [
                    FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=red:size=1280x720:rate=30:duration=1",
                    "-f", "lavfi", "-i", "color=c=blue:size=1280x720:rate=30:duration=1",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                    "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
                    "-map", "[v]", "-map", "2:a",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(source),
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )

            cuts = detect_scene_cuts(source, FFMPEG)
            self.assertTrue(any(0.7 <= t <= 1.3 for t in cuts), cuts)

            analyzed = analyze_reframe(source, FFMPEG)
            self.assertIsNotNone(analyzed)
            self.assertEqual(analyzed[0].start, 0.0)
            self.assertGreater(analyzed[-1].end, 1.5)

            explicit_plan = [
                ShotPlan(0.0, 0.7, "crop", 20, 0, 404, 720),
                ShotPlan(0.7, 1.3, "split", 0, 0, 404, 720),
                ShotPlan(1.3, 2.0, "crop", 850, 0, 404, 720),
            ]
            out = work / "smart_fill.mp4"
            render_clip(
                source,
                out,
                [Word("halo", 0.2, 0.8), Word("semua", 0.9, 1.7)],
                FFMPEG,
                2.0,
                hook_text="SMART FILL",
                portrait=True,
                background="fill",
                reframe_shots=explicit_plan,
            )
            self.assertTrue(out.is_file())
            self.assertGreater(out.stat().st_size, 1000)
            self.assertEqual(probe_size(out, FFMPEG), (1080, 1920))


if __name__ == "__main__":
    unittest.main()
