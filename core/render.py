"""FFmpeg rendering: 9:16 reframe, hook, word captions, watermark."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .subtitles import Word

_ASS_HEADER = """[Script Info]
Title: AIKLIPYT captions
ScriptType: v4.00+
WrapStyle: 0
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Arial Black,{caption_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,2,{margin},{margin},{bottom_margin},1
Style: CaptionBg,Arial Black,{caption_size},&H00FFFFFF,&H000000FF,&H00031410,&H80000000,-1,0,0,0,100,100,0,0,3,18,0,2,{margin},{margin},{bottom_margin},1
Style: Hook,Arial Black,{hook_size},{hook_color},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,2,8,{margin},{margin},{top_margin},1
Style: Credit,Arial,{credit_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,3,{margin},{margin},{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

_WHITE = r"{\c&H00FFFFFF&}"
_CAPTION_STYLES = (
    "highlight",
    "box",
    "pop",
    "smart-bg-focus",
    "box-highlight",
    "word-focus",
    "underline-focus",
    "outline-focus",
)


def _ass_color(value: str, fallback: str = "#FFD700") -> str:
    value = (value or "").strip()
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        value = fallback
    return f"&H00{value[5:7]}{value[3:5]}{value[1:3]}&".upper()


def _color_tag(color: str) -> str:
    return r"{\c" + color + "}"


def ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, sec = divmod(rest, 60)
    return f"{int(hours)}:{int(minutes):02d}:{sec:05.2f}"


def ass_escape(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace("{", "(")
        .replace("}", ")")
        .replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )


def _groups(words: list[Word]) -> list[list[Word]]:
    groups: list[list[Word]] = []
    current: list[Word] = []
    for word in words:
        if current:
            gap = word.start - current[-1].end
            length = len(" ".join(w.word for w in current))
            span = word.end - current[0].start
            if gap > 1.0 or length + len(word.word) > 20 or len(current) >= 4 or span > 3.6:
                groups.append(current)
                current = []
        current.append(word)
    if current:
        groups.append(current)
    return groups


def build_ass(
    words: list[Word],
    hook_text: str = "",
    credit: str = "",
    hook_seconds: float = 3.0,
    duration: float | None = None,
    width: int = 1080,
    height: int = 1920,
    caption_color: str = "#FFD700",
    caption_style: str = "highlight",
) -> str:
    portrait = height >= width
    accent = _ass_color(caption_color)
    if caption_style not in _CAPTION_STYLES:
        caption_style = "highlight"
    header = _ASS_HEADER.format(
        width=width,
        height=height,
        caption_size=62 if portrait else 54,
        hook_size=86 if portrait else 64,
        credit_size=40 if portrait else 32,
        margin=60 if portrait else 40,
        bottom_margin=260 if portrait else 80,
        top_margin=220 if portrait else 70,
        hook_color=accent,
    )
    events: list[str] = []
    end_of_video = duration or (words[-1].end if words else 0.0)

    if hook_text.strip():
        hook_end = min(max(0.5, hook_seconds), max(0.5, end_of_video)) if end_of_video else max(0.5, hook_seconds)
        events.append(
            f"Dialogue: 0,{ass_time(0)},{ass_time(hook_end)},Hook,,0,0,0,,{ass_escape(hook_text).upper()}"
        )

    for group in _groups(words):
        event_style = "CaptionBg" if caption_style == "smart-bg-focus" else "Caption"
        for index, word in enumerate(group):
            start = word.start
            end = group[index + 1].start if index + 1 < len(group) else word.end + 0.12
            end = max(start + 0.06, end)
            if caption_style == "box-highlight":
                token = ass_escape(word.word)
                if token:
                    text = f"{{\\c&H000000&\\3c{accent}\\bord14\\shad0}}{token}{{\\rCaption}}"
                    events.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Caption,,0,0,0,,{text}")
                continue
            parts = []
            for other_index, other in enumerate(group):
                token = ass_escape(other.word)
                if not token:
                    continue
                if caption_style == "underline-focus":
                    token = token.upper()
                if other_index == index:
                    if caption_style == "box":
                        parts.append(f"{{\\c&H000000&\\3c{accent}\\bord10}}" + token + r"{\rCaption}")
                    elif caption_style == "pop":
                        parts.append(_color_tag(accent) + r"{\fscx115\fscy115}" + token + r"{\rCaption}")
                    elif caption_style == "smart-bg-focus":
                        parts.append(_color_tag(accent) + token + r"{\rCaptionBg}")
                    elif caption_style == "word-focus":
                        parts.append(r"{\alpha&H00&}" + _color_tag(accent) + r"{\fscx110\fscy110}" + token + r"{\rCaption}")
                    elif caption_style == "underline-focus":
                        parts.append(_color_tag(accent) + r"{\u1}" + token + r"{\rCaption}")
                    elif caption_style == "outline-focus":
                        parts.append(f"{{\\1a&H00&\\c{accent}\\3c{accent}\\bord3\\shad0}}" + token + r"{\rCaption}")
                    else:
                        parts.append(_color_tag(accent) + token + _WHITE)
                else:
                    if caption_style == "word-focus":
                        parts.append(r"{\alpha&H80&}" + token + r"{\rCaption}")
                    elif caption_style == "outline-focus":
                        parts.append(r"{\1a&HFF&\3c&HFFFFFF&\bord3\shad0}" + token + r"{\rCaption}")
                    else:
                        parts.append(token)
            if not parts:
                continue
            text = " ".join(parts)
            events.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},{event_style},,0,0,0,,{text}")

    if credit.strip():
        events.append(
            f"Dialogue: 0,{ass_time(0)},{ass_time(max(1.0, end_of_video))},Credit,,0,0,0,,{ass_escape(credit)}"
        )

    return header + "\n".join(events) + "\n"


_HW_ENCODERS = [
    ("h264_nvenc", ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "23", "-b:v", "0"]),
    ("h264_qsv", ["-c:v", "h264_qsv", "-global_quality", "23"]),
    ("h264_amf", ["-c:v", "h264_amf", "-quality", "balanced", "-qp_i", "22", "-qp_p", "22"]),
]
_CPU_ARGS = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21"]
_ENCODER_STATUS: dict[str, bool] = {}
_PROBE_CACHE: dict[tuple[str, str], bool] = {}
_PROBE_ERRORS: dict[str, str] = {}


def _probe_encoder(ffmpeg: str, name: str, args: list[str]) -> bool:
    key = (ffmpeg, name)
    if key in _PROBE_CACHE:
        return _PROBE_CACHE[key]
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.2",
        "-frames:v", "1", *args, "-pix_fmt", "yuv420p", "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30,
            creationflags=0x08000000,
        )
        ok = proc.returncode == 0
        if not ok:
            lines = proc.stderr.decode("utf-8", "replace").strip().splitlines()
            _PROBE_ERRORS[name] = (lines[-1] if lines else f"exit {proc.returncode}")[:160]
    except (OSError, subprocess.TimeoutExpired):
        ok = False
        _PROBE_ERRORS[name] = "probe timeout"
    _PROBE_CACHE[key] = ok
    return ok


def detect_encoder(ffmpeg: str) -> str | None:
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True,
            timeout=30,
            creationflags=0x08000000,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
    for name, args in _HW_ENCODERS:
        if re.search(rf"\s{name}\s", text) and _probe_encoder(ffmpeg, name, args):
            return name
    return None


def _portrait_chain(background: str) -> str:
    if background == "blurred":
        return (
            "split=2[bg][fg];"
            "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=24[bg2];"
            "[fg]scale=1080:1920:force_original_aspect_ratio=decrease[fg2];"
            "[bg2][fg2]overlay=(W-w)/2:(H-h)/2"
        )
    return (
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black"
    )


def _filter_complex(portrait: bool, background: str, use_ass: bool, logo: Path | None, logo_opacity: float) -> str:
    chain = _portrait_chain(background) if portrait else (
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black"
    )
    graph = f"[0:v]{chain}"
    if use_ass:
        graph += ",ass=captions.ass"
    if logo is not None:
        graph += "[base];[1:v]scale=200:-2,format=rgba,colorchannelmixer=aa={:.2f}[logo];[base][logo]overlay=W-w-40:40[v]".format(
            max(0.05, min(1.0, logo_opacity))
        )
    else:
        graph += "[v]"
    return graph


def render_clip(
    input_path: Path,
    output_path: Path,
    words: list[Word],
    ffmpeg: str,
    duration: float,
    hook_text: str = "",
    credit: str = "",
    hook_seconds: float = 3.0,
    portrait: bool = True,
    background: str = "black",
    captions: bool = True,
    hook: bool = True,
    watermark: str = "",
    logo_opacity: float = 0.9,
    caption_color: str = "#FFD700",
    caption_style: str = "highlight",
    on_progress=None,
    on_log=None,
) -> Path:
    if not ffmpeg:
        raise RuntimeError("ffmpeg was not found. Put ffmpeg.exe in assets/ffmpeg or install it on PATH.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workdir = output_path.parent
    use_ass = bool((captions and words) or (hook and hook_text.strip()) or credit.strip())
    if use_ass:
        (workdir / "captions.ass").write_text(
            build_ass(
                words if captions else [],
                hook_text if hook else "",
                credit,
                hook_seconds,
                duration,
                1080 if portrait else 1920,
                1920 if portrait else 1080,
                caption_color=caption_color,
                caption_style=caption_style,
            ),
            encoding="utf-8",
        )

    logo = Path(watermark) if watermark and Path(watermark).is_file() else None
    if watermark and logo is None and on_log:
        on_log("Watermark file not found, skipping logo")

    graph = _filter_complex(portrait, background, use_ass, logo, logo_opacity)
    base_cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
    ]
    if logo is not None:
        base_cmd += ["-i", str(logo)]
    base_cmd += [
        "-filter_complex",
        graph,
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-progress",
        "pipe:1",
        "-nostats",
        str(output_path),
    ]

    hardware = detect_encoder(ffmpeg)
    if hardware is None and on_log and _PROBE_ERRORS:
        detail = "; ".join(f"{name}: {error}" for name, error in _PROBE_ERRORS.items())
        on_log(f"Hardware encoder tidak tersedia ({detail}); memakai libx264")
    if hardware and _ENCODER_STATUS.get(hardware) is False:
        hardware = None
    attempts: list[tuple[str, list[str]]] = []
    for name, args in _HW_ENCODERS:
        if name == hardware:
            attempts.append((name, args))
            break
    attempts.append(("libx264", _CPU_ARGS))

    last_error = ""
    for name, video_args in attempts:
        cmd = base_cmd[:-1] + video_args + [str(output_path)]
        if on_log:
            on_log(f"Rendering with {name}")
        if output_path.exists():
            output_path.unlink()
        process = subprocess.Popen(
            cmd,
            cwd=str(workdir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=0x08000000,
        )
        tail: list[str] = []
        try:
            assert process.stdout is not None
            for raw in process.stdout:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                tail = (tail + [line])[-30:]
                match = re.match(r"out_time_us=(\d+)", line)
                if match and duration > 0 and on_progress:
                    percent = min(99.0, float(match.group(1)) / 1_000_000 / duration * 100)
                    on_progress(percent)
            process.wait(timeout=1800)
        except subprocess.TimeoutExpired:
            process.kill()
            last_error = "ffmpeg timed out"
            continue
        finally:
            if process.stdout:
                process.stdout.close()
        if process.returncode == 0 and output_path.exists() and output_path.stat().st_size > 1000:
            _ENCODER_STATUS[name] = True
            if on_progress:
                on_progress(100.0)
            return output_path
        last_error = "\n".join(tail[-8:]) or f"ffmpeg exited with {process.returncode}"
        _ENCODER_STATUS[name] = False
        if on_log:
            on_log(f"{name} failed, trying fallback")
    raise RuntimeError(f"ffmpeg failed: {last_error}")


def probe_size(path: Path, ffmpeg: str) -> tuple[int, int] | None:
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)],
        capture_output=True,
        timeout=30,
        creationflags=0x08000000,
    )
    match = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", proc.stderr.decode("utf-8", "replace"))
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))
