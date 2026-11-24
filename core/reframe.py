"""Shot-locked face and active-speaker 9:16 reframing for Layar Penuh (fill) mode."""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_SCD_TIME = re.compile(r"lavfi\.scd\.time:\s*([0-9]+(?:\.[0-9]+)?)")
_YUNET_MODEL = Path(__file__).resolve().parent.parent / "assets" / "models" / "face_detection_yunet_2023mar.onnx"


@dataclass(frozen=True)
class ShotPlan:
    start: float
    end: float
    mode: str  # "crop" or "split"
    crop_x: int
    crop_y: int
    crop_w: int
    crop_h: int


def detect_scene_cuts(
    input_path: Path,
    ffmpeg: str,
    threshold: float = 12.0,
    timeout: int = 120,
) -> list[float]:
    if not ffmpeg:
        return []
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "info",
        "-i",
        str(input_path),
        "-vf",
        f"scdet=t={threshold}",
        "-f",
        "null",
        "-",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            creationflags=_CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    text = proc.stderr.decode("utf-8", "replace")
    cuts = {float(match.group(1)) for match in _SCD_TIME.finditer(text)}
    return sorted(t for t in cuts if t > 0.0)


def _build_shot_ranges(
    cuts: list[float],
    duration: float,
    min_shot: float = 0.6,
    max_shots: int = 30,
) -> list[tuple[float, float]]:
    if duration <= 0.0:
        return []
    max_cuts = max(0, max_shots - 1)
    accepted: list[float] = []
    prev = 0.0
    for ts in sorted(set(cuts)):
        if ts < prev + min_shot or ts > duration - min_shot:
            continue
        accepted.append(ts)
        prev = ts
        if len(accepted) >= max_cuts:
            break
    boundaries = [0.0, *accepted, duration]
    return list(zip(boundaries[:-1], boundaries[1:]))


def _compute_crop_size(src_w: int, src_h: int) -> tuple[int, int] | None:
    if src_w <= 0 or src_h <= 0 or src_w / src_h <= 9 / 16 + 0.05:
        return None
    crop_h = max(2, src_h - (src_h % 2))
    crop_w = min(src_w, int(round(crop_h * 9 / 16)))
    crop_w = max(2, crop_w - (crop_w % 2))
    return crop_w, crop_h


def _create_detector(cv2, width: int, height: int, model_path: Path | None = None):
    path = model_path or _YUNET_MODEL
    if not path.is_file() or not hasattr(cv2, "FaceDetectorYN"):
        return None
    return cv2.FaceDetectorYN.create(str(path), "", (max(1, width), max(1, height)), 0.6, 0.3, 10)


def _detect_faces_yunet(detector, small_bgr, scale: float) -> list[dict]:
    h, w = small_bgr.shape[:2]
    if h < 2 or w < 2:
        return []
    detector.setInputSize((w, h))
    _, raw = detector.detect(small_bgr)
    if raw is None or len(raw) == 0:
        return []

    faces: list[dict] = []
    for row in raw:
        sx = int(round(float(row[0])))
        sy = int(round(float(row[1])))
        sw = max(1, int(round(float(row[2]))))
        sh = max(1, int(round(float(row[3]))))
        eye_y_small = (float(row[5]) + float(row[7])) / 2.0

        pad = max(6, int(sw * 0.22))
        mx_min = min(float(row[10]), float(row[12]))
        mx_max = max(float(row[10]), float(row[12]))
        my_min = min(float(row[11]), float(row[13]))
        my_max = max(float(row[11]), float(row[13]))
        mx0 = max(0, min(w - 2, int(round(mx_min - pad))))
        my0 = max(0, min(h - 2, int(round(my_min - pad))))
        mx1 = max(mx0 + 1, min(w, int(round(mx_max + pad))))
        my1 = max(my0 + 1, min(h, int(round(my_max + pad))))

        faces.append(
            {
                "box": (
                    int(round(sx * scale)),
                    int(round(sy * scale)),
                    max(1, int(round(sw * scale))),
                    max(1, int(round(sh * scale))),
                ),
                "small_box": (sx, sy, sw, sh),
                "eye_y": eye_y_small * scale,
                "mouth_box": (mx0, my0, mx1, my1),
            }
        )
    return faces


def _choose_shot_framing(
    tracks: list[dict],
    src_w: int,
    src_h: int,
    crop_w: int,
    crop_h: int,
) -> tuple[str, int, int]:
    def _clamp_crop(cx: float, cy: float) -> tuple[int, int]:
        x = max(0, min(src_w - crop_w, int(round(cx - crop_w / 2))))
        y = max(0, min(src_h - crop_h, int(round(cy - crop_h * 0.36))))
        x -= x % 2
        y -= y % 2
        return x, y

    if not tracks:
        cx = max(0, (src_w - crop_w) // 2)
        cy = max(0, (src_h - crop_h) // 2)
        return "crop", cx - (cx % 2), cy - (cy % 2)

    if len(tracks) == 1:
        x, y = _clamp_crop(tracks[0]["cx"], tracks[0]["cy"])
        return "crop", x, y

    ranked = sorted(tracks, key=lambda t: (t.get("count", 1), t["fw"] * t["fh"]), reverse=True)
    t1, t2 = ranked[0], ranked[1]
    if abs(t1["cx"] - t2["cx"]) + (t1["fw"] + t2["fw"]) * 0.5 <= crop_w * 0.85:
        x, y = _clamp_crop((t1["cx"] + t2["cx"]) / 2, (t1["cy"] + t2["cy"]) / 2)
        return "crop", x, y

    m1, m2 = float(t1.get("motion", 0.0)), float(t2.get("motion", 0.0))
    winner = t1 if m1 >= m2 else t2
    max_m, min_m = max(m1, m2), min(m1, m2)
    if max_m >= 1.35 * max(min_m, 1.0) and max_m >= 4.0:
        x, y = _clamp_crop(winner["cx"], winner["cy"])
        return "crop", x, y

    if min(t1["cx"], t2["cx"]) < src_w * 0.48 and max(t1["cx"], t2["cx"]) > src_w * 0.52:
        return "split", 0, 0

    x, y = _clamp_crop(t1["cx"], t1["cy"])
    return "crop", x, y


def _merge_similar_shots(shots: list[ShotPlan], src_w: int, src_h: int) -> list[ShotPlan]:
    if not shots:
        return []
    tol_x = max(24, int(src_w * 0.04))
    tol_y = max(24, int(src_h * 0.04))
    merged = [shots[0]]
    for cur in shots[1:]:
        prev = merged[-1]
        same_kind = prev.mode == cur.mode and prev.crop_w == cur.crop_w and prev.crop_h == cur.crop_h
        close_crop = (
            prev.mode == "split"
            or (abs(prev.crop_x - cur.crop_x) <= tol_x and abs(prev.crop_y - cur.crop_y) <= tol_y)
        )
        if same_kind and close_crop:
            d1 = max(0.01, prev.end - prev.start)
            d2 = max(0.01, cur.end - cur.start)
            if prev.mode == "split":
                nx, ny = 0, 0
            else:
                nx = int(round((prev.crop_x * d1 + cur.crop_x * d2) / (d1 + d2)))
                ny = int(round((prev.crop_y * d1 + cur.crop_y * d2) / (d1 + d2)))
                nx = max(0, min(src_w - prev.crop_w, nx))
                ny = max(0, min(src_h - prev.crop_h, ny))
                nx -= nx % 2
                ny -= ny % 2
            merged[-1] = ShotPlan(prev.start, cur.end, prev.mode, nx, ny, prev.crop_w, prev.crop_h)
        else:
            merged.append(cur)
    return merged


def _mouth_patch(cv2, gray, mouth_box: tuple[int, int, int, int]):
    mx0, my0, mx1, my1 = mouth_box
    h, w = gray.shape[:2]
    x0 = max(0, min(w - 1, mx0))
    y0 = max(0, min(h - 1, my0))
    x1 = max(x0 + 1, min(w, mx1))
    y1 = max(y0 + 1, min(h, my1))
    return cv2.resize(gray[y0:y1, x0:x1], (24, 16))


def analyze_reframe(input_path: Path, ffmpeg: str, on_log=None) -> list[ShotPlan] | None:
    try:
        import cv2
        import numpy as np  # noqa: F401
    except ImportError:
        if on_log:
            on_log("OpenCV tidak tersedia; memakai center crop 9:16")
        return None

    cap = cv2.VideoCapture(str(input_path))
    try:
        if not cap.isOpened():
            return None
        src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = frame_count / fps if fps > 0 and frame_count > 0 else 0.0
        crop_size = _compute_crop_size(src_w, src_h)
        if duration <= 0.0 or crop_size is None:
            return None
        crop_w, crop_h = crop_size

        scale = src_w / 640.0 if src_w > 640 else 1.0
        small_w = min(src_w, 640)
        small_h = max(1, int(round(src_h / scale)))
        detector = _create_detector(cv2, small_w, small_h)
        if detector is None:
            if on_log:
                on_log("Model deteksi wajah YuNet tidak ditemukan; memakai center crop 9:16")
            return None

        cuts = detect_scene_cuts(input_path, ffmpeg)
        ranges = _build_shot_ranges(cuts, duration)
        if not ranges:
            return None

        per_shot = max(2, min(5, 60 // len(ranges)))
        if len(ranges) <= 12:
            per_shot = max(3, per_shot)

        plans: list[ShotPlan] = []
        for start, end in ranges:
            span = max(0.0, end - start)
            pad = min(0.15, span * 0.15)
            usable = max(0.0, span - 2 * pad)
            if per_shot == 1 or usable <= 0:
                timestamps = [start + span / 2]
            else:
                timestamps = [
                    start + pad + usable * idx / (per_shot - 1)
                    for idx in range(per_shot)
                ]

            tracks: list[dict] = []
            for ts in timestamps:
                cap.set(cv2.CAP_PROP_POS_MSEC, ts * 1000.0)
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue
                fh_orig, fw_orig = frame.shape[:2]
                if fw_orig > 640:
                    f_scale = fw_orig / 640.0
                    small = cv2.resize(frame, (640, max(1, int(round(fh_orig / f_scale)))))
                else:
                    f_scale = 1.0
                    small = frame
                gray_small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                faces = _detect_faces_yunet(detector, small, f_scale)

                for face in faces:
                    fx, _fy, fw, fh = face["box"]
                    cx = fx + fw / 2.0
                    cy = float(face["eye_y"])
                    patch = _mouth_patch(cv2, gray_small, face["mouth_box"])

                    best = None
                    best_dist = float("inf")
                    for tr in tracks:
                        dist = abs(cx - tr["cx"])
                        if dist <= src_w * 0.15 and dist < best_dist:
                            best = tr
                            best_dist = dist

                    if best is None:
                        tracks.append(
                            {
                                "cx": cx,
                                "cy": cy,
                                "fw": float(fw),
                                "fh": float(fh),
                                "count": 1,
                                "motion": 0.0,
                                "motion_samples": 0,
                                "last_patch": patch,
                            }
                        )
                    else:
                        n = best["count"]
                        best["cx"] = (best["cx"] * n + cx) / (n + 1)
                        best["cy"] = (best["cy"] * n + cy) / (n + 1)
                        best["fw"] = (best["fw"] * n + fw) / (n + 1)
                        best["fh"] = (best["fh"] * n + fh) / (n + 1)
                        best["count"] = n + 1
                        if best["last_patch"] is not None:
                            diff = float(cv2.absdiff(best["last_patch"], patch).mean())
                            ms = best["motion_samples"]
                            best["motion"] = (best["motion"] * ms + diff) / (ms + 1)
                            best["motion_samples"] = ms + 1
                        best["last_patch"] = patch

            if len(timestamps) >= 3:
                steady = [tr for tr in tracks if tr["count"] >= 2]
                if steady:
                    tracks = steady

            mode, crop_x, crop_y = _choose_shot_framing(tracks, src_w, src_h, crop_w, crop_h)
            plans.append(ShotPlan(start, end, mode, crop_x, crop_y, crop_w, crop_h))

        return _merge_similar_shots(plans, src_w, src_h) or None
    finally:
        cap.release()
