"""FFmpeg rendering: 9:16 reframe, hook, word captions, watermark."""
from __future__ import annotations

import os
import re
import subprocess
import threading
from pathlib import Path

from .subtitles import Word

_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

_ASS_HEADER = """[Script Info]
Title: AIKLIPYT captions
ScriptType: v4.00+
WrapStyle: 0
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{caption_font},{caption_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,{caption_bold},0,0,0,100,100,0,0,1,4,1,2,{margin},{margin},{bottom_margin},1
Style: CaptionBg,{caption_font},{caption_size},&H00FFFFFF,&H000000FF,&H00031410,&H80000000,{caption_bold},0,0,0,100,100,0,0,3,18,0,2,{margin},{margin},{bottom_margin},1
Style: Hook,Arial Black,{hook_size},{hook_color},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,2,8,{margin},{margin},{top_margin},1
Style: HookBox,Arial Black,{hook_box_size},&H00101210,&H000000FF,&H00FFFFFF,&H80000000,-1,0,0,0,100,100,0,0,3,18,0,8,{margin},{margin},{top_margin},1
Style: Credit,Arial,{credit_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,3,{margin},{margin},{margin},1
Style: CaptionAlt,{caption_font},{alt_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,{caption_bold},0,0,0,100,100,0,0,1,3,1,2,{margin},{margin},{alt_margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

_WHITE = r"{\c&H00FFFFFF&}"
CAPTION_STYLES = (
    "highlight",
    "box",
    "pop",
    "smart-bg-focus",
    "box-highlight",
    "word-focus",
    "underline-focus",
    "outline-focus",
    "temp-0",
    "hormozi",
    "karaoke",
    "gadzhi",
    "mrbeast",
    "bilingual",
)
HOOK_STYLES = (
    "classic",
    "card",
    "quote",
    "accent-bar",
    "cinema",
    "neon",
    "breaking",
    "impact",
    "tape",
    "spotlight",
)
CAPTION_FONTS = (
    "Arial Black",
    "Arial",
    "Impact",
    "Segoe UI",
    "Bahnschrift",
    "Verdana",
    "Tahoma",
    "Trebuchet MS",
    "Calibri",
    "Georgia",
    "Times New Roman",
    "Comic Sans MS",
    "Consolas",
)
MRBEAST_COLORS = (
    "&H0000D7FF&",  # gold (default accent)
    "&H0000FF00&",  # green
    "&H00FF00FF&",  # magenta
    "&H000000FF&",  # red (ASS BGR)
    "&H00FFD700&",  # cyan
    "&H00FF8000&",  # sky blue
)


def _ass_color(value: str, fallback: str = "#FFD700") -> str:
    value = (value or "").strip()
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        value = fallback
    return f"&H00{value[5:7]}{value[3:5]}{value[1:3]}&".upper()


def _color_tag(color: str) -> str:
    return r"{\c" + color + "}"


def ass_time(seconds: float) -> str:
    centis = int(round(max(0.0, seconds) * 100))
    hours, rest = divmod(centis, 360000)
    minutes, rest = divmod(rest, 6000)
    sec, cs = divmod(rest, 100)
    return f"{hours}:{minutes:02d}:{sec:02d}.{cs:02d}"


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


group_words = _groups  # public alias for the pipeline's bilingual grouping


def _credit_tag(position: str, width: int, height: int, margin: int, opacity: float = 1.0) -> str:
    mapping = {
        "top-left": (7, margin, margin),
        "top-center": (8, width // 2, margin),
        "top-right": (9, width - margin, margin),
        "middle-left": (4, margin, height // 2),
        "center": (5, width // 2, height // 2),
        "middle-right": (6, width - margin, height // 2),
        "bottom-left": (1, margin, height - margin),
        "bottom-center": (2, width // 2, height - margin),
        "bottom-right": (3, width - margin, height - margin),
    }
    align, x, y = mapping.get(position, mapping["bottom-center"])
    alpha = int(round((1.0 - max(0.0, min(1.0, opacity))) * 255))
    fade = "" if alpha == 0 else rf"\alpha&H{alpha:02X}&"
    return rf"{{\an{align}\pos({x},{y}){fade}}}"


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
    caption_font: str = "Arial Black",
    caption_bold: bool = True,
    hook_style: str = "classic",
    credit_position: str = "bottom-center",
    credit_opacity: float = 1.0,
    translations: list[str] | None = None,
) -> str:
    portrait = height >= width
    margin = 60 if portrait else 40
    accent = _ass_color(caption_color)
    if caption_style not in CAPTION_STYLES:
        caption_style = "highlight"
    if caption_font not in CAPTION_FONTS:
        caption_font = "Arial Black"
    if hook_style not in HOOK_STYLES:
        hook_style = "classic"
    bold_flag = -1 if caption_bold else 0
    gadzhi_font = "Arial" if caption_font == "Arial Black" else caption_font
    gadzhi_base = rf"{{\fn{gadzhi_font}\b0\bord1\shad0\3c&H000000&}}"
    header = _ASS_HEADER.format(
        width=width,
        height=height,
        caption_font=caption_font,
        caption_bold=bold_flag,
        caption_size=62 if portrait else 54,
        hook_size=86 if portrait else 64,
        hook_box_size=68 if portrait else 52,
        credit_size=40 if portrait else 32,
        alt_size=46 if portrait else 38,
        margin=margin,
        bottom_margin=260 if portrait else 80,
        top_margin=220 if portrait else 70,
        alt_margin=(260 if portrait else 80) + 96,
        hook_color=accent,
    )
    events: list[str] = []
    end_of_video = duration or (words[-1].end if words else 0.0)

    if hook_text.strip():
        hook_end = min(max(0.5, hook_seconds), max(0.5, end_of_video)) if end_of_video else max(0.5, hook_seconds)
        escaped_hook = ass_escape(hook_text)
        if hook_style == "card":
            events.append(
                f"Dialogue: 0,{ass_time(0)},{ass_time(hook_end)},HookBox,,0,0,0,,{{\\fad(180,180)}}{escaped_hook}"
            )
        elif hook_style == "quote":
            events.append(
                f"Dialogue: 0,{ass_time(0)},{ass_time(hook_end)},HookBox,,0,0,0,,{{\\c{accent}\\3c&H00141414&\\fad(180,180)}}“ {{\\c&H00FFFFFF&}}{escaped_hook}"
            )
        elif hook_style == "accent-bar":
            events.append(
                f"Dialogue: 0,{ass_time(0)},{ass_time(hook_end)},HookBox,,0,0,0,,{{\\c&H00101210&\\3c{accent}\\fad(160,160)}}{escaped_hook.upper()}"
            )
        elif hook_style == "cinema":
            events.append(
                f"Dialogue: 0,{ass_time(0)},{ass_time(hook_end)},Hook,,0,0,0,,{{\\c&H00FFFFFF&\\b0\\fsp6\\bord2\\shad2\\3c&H000000&\\fad(300,250)}}{escaped_hook.upper()}"
            )
        elif hook_style == "neon":
            events.append(
                f"Dialogue: 0,{ass_time(0)},{ass_time(hook_end)},Hook,,0,0,0,,{{\\c&H00FFFFFF&\\3c{accent}\\bord7\\blur10\\shad0\\fad(160,160)}}{escaped_hook.upper()}"
            )
        elif hook_style == "breaking":
            events.append(
                f"Dialogue: 0,{ass_time(0)},{ass_time(hook_end)},HookBox,,0,0,0,,{{\\c&H00FFFFFF&\\3c&H002222E0&\\fad(140,140)}}● {escaped_hook.upper()}"
            )
        elif hook_style == "impact":
            events.append(
                f"Dialogue: 0,{ass_time(0)},{ass_time(hook_end)},Hook,,0,0,0,,{{\\c&H00FFFFFF&\\3c&H000000&\\bord10\\shad4\\fscx132\\fscy132\\t(0,180,\\fscx100\\fscy100)}}{escaped_hook.upper()}"
            )
        elif hook_style == "tape":
            events.append(
                f"Dialogue: 0,{ass_time(0)},{ass_time(hook_end)},HookBox,,0,0,0,,{{\\frz3\\c&H00101210&\\3c&H00D8F5FF&\\fad(160,160)}}{escaped_hook}"
            )
        elif hook_style == "spotlight":
            hook_words = escaped_hook.upper().split()
            split_at = min(2, max(1, len(hook_words) // 2))
            lead = " ".join(hook_words[:split_at])
            rest = " ".join(hook_words[split_at:])
            styled = f"{{\\i1\\c{accent}\\bord5\\shad3\\fad(200,180)}}{lead}" + (f" {{\\c&H00FFFFFF&}}{rest}" if rest else "")
            events.append(
                f"Dialogue: 0,{ass_time(0)},{ass_time(hook_end)},Hook,,0,0,0,,{styled}"
            )
        else:
            events.append(
                f"Dialogue: 0,{ass_time(0)},{ass_time(hook_end)},Hook,,0,0,0,,{escaped_hook.upper()}"
            )

    groups = group_words(words)
    for group_index, group in enumerate(groups):
        next_start = groups[group_index + 1][0].start if group_index + 1 < len(groups) else None
        group_end = group[-1].end + 0.12
        if next_start is not None and next_start > group[-1].start:
            group_end = min(group_end, next_start)
        if caption_style == "karaoke":
            kf = []
            for i, w in enumerate(group):
                dur = (group[i + 1].start - w.start) if i + 1 < len(group) else (w.end - w.start)
                kf.append(r"{\kf" + str(max(1, int(round(dur * 100)))) + "}" + ass_escape(w.word))
            if kf:
                text = r"{\2c&H00FFFFFF&}" + _color_tag(accent) + " ".join(kf)
                line_end = group_end if group_end > group[0].start else group[0].start + 0.06
                events.append(
                    f"Dialogue: 0,{ass_time(group[0].start)},{ass_time(line_end)},Caption,,0,0,0,,{text}"
                )
            continue
        event_style = "CaptionBg" if caption_style == "smart-bg-focus" else "Caption"
        for index, word in enumerate(group):
            start = word.start
            end = group[index + 1].start if index + 1 < len(group) else group_end
            if end <= start:
                end = start + 0.06
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
                if caption_style in ("underline-focus", "temp-0", "hormozi", "mrbeast"):
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
                    elif caption_style == "temp-0":
                        parts.append(f"{{\\shad0\\c{accent}\\3c&H000000&\\bord4}}" + token + r"{\rCaption}")
                    elif caption_style == "hormozi":
                        parts.append(f"{{\\c{accent}\\bord12\\3c&H000000&\\shad2\\fscx118\\fscy118}}" + token + r"{\rCaption}")
                    elif caption_style == "gadzhi":
                        parts.append(_color_tag(accent) + gadzhi_base + token + r"{\rCaption}" + gadzhi_base)
                    elif caption_style == "mrbeast":
                        color = MRBEAST_COLORS[other_index % len(MRBEAST_COLORS)]
                        parts.append(f"{{\\c{color}\\bord8\\3c&HFFFFFF&\\shad2\\fscx120\\fscy120}}" + token + r"{\rCaption}")
                    else:
                        parts.append(_color_tag(accent) + token + _WHITE)
                else:
                    if caption_style == "word-focus":
                        parts.append(r"{\alpha&H80&}" + token + r"{\rCaption}")
                    elif caption_style == "outline-focus":
                        parts.append(r"{\1a&HFF&\3c&HFFFFFF&\bord3\shad0}" + token + r"{\rCaption}")
                    elif caption_style == "temp-0":
                        parts.append(r"{\shad0}" + token)
                    elif caption_style == "hormozi":
                        parts.append(r"{\bord12\3c&H000000&\shad2}" + token)
                    elif caption_style == "gadzhi":
                        parts.append(gadzhi_base + token)
                    elif caption_style == "mrbeast":
                        parts.append(r"{\bord8\3c&H000000&\shad2}" + token)
                    else:
                        parts.append(token)
            if not parts:
                continue
            text = " ".join(parts)
            events.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},{event_style},,0,0,0,,{text}")
        if caption_style == "bilingual" and translations and group_index < len(translations):
            translated = (translations[group_index] or "").strip()
            if translated:
                alt_end = group_end if group_end > group[0].start else group[0].start + 0.06
                events.append(
                    f"Dialogue: 0,{ass_time(group[0].start)},{ass_time(alt_end)},CaptionAlt,,0,0,0,,{ass_escape(translated)}"
                )

    if credit.strip():
        events.append(
            f"Dialogue: 0,{ass_time(0)},{ass_time(max(1.0, end_of_video))},Credit,,0,0,0,,{_credit_tag(credit_position, width, height, margin, credit_opacity)}{ass_escape(credit)}"
        )

    return header + "\n".join(events) + "\n"


_HW_ENCODERS = [
    ("h264_nvenc", ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "23", "-b:v", "0"]),
    ("h264_qsv", ["-c:v", "h264_qsv", "-global_quality", "23"]),
    ("h264_amf", ["-c:v", "h264_amf", "-quality", "balanced", "-qp_i", "22", "-qp_p", "22"]),
]
_CPU_ARGS = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21"]
_ENCODER_LOCK = threading.RLock()
_ENCODER_STATUS: dict[str, bool] = {}
_PROBE_CACHE: dict[tuple[str, str], bool] = {}
_PROBE_ERRORS: dict[tuple[str, str], str] = {}
_ENCODER_LIST_CACHE: dict[str, str] = {}


def _probe_encoder(ffmpeg: str, name: str, args: list[str]) -> bool:
    key = (ffmpeg, name)
    with _ENCODER_LOCK:
        if key in _PROBE_CACHE:
            return _PROBE_CACHE[key]
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.2",
        "-frames:v", "1", *args, "-pix_fmt", "yuv420p", "-f", "null", "-",
    ]
    error = ""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30,
            creationflags=_CREATE_NO_WINDOW,
        )
        ok = proc.returncode == 0
        if not ok:
            lines = proc.stderr.decode("utf-8", "replace").strip().splitlines()
            error = (lines[-1] if lines else f"exit {proc.returncode}")[:160]
    except (OSError, subprocess.TimeoutExpired):
        ok = False
        error = "probe timeout"
    with _ENCODER_LOCK:
        _PROBE_CACHE[key] = ok
        if error:
            _PROBE_ERRORS[key] = error
    return ok


def detect_encoder(ffmpeg: str) -> str | None:
    with _ENCODER_LOCK:
        text = _ENCODER_LIST_CACHE.get(ffmpeg)
    if text is None:
        try:
            proc = subprocess.run(
                [ffmpeg, "-hide_banner", "-encoders"],
                capture_output=True,
                timeout=30,
                creationflags=_CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        text = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
        with _ENCODER_LOCK:
            _ENCODER_LIST_CACHE[ffmpeg] = text
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


def _logo_xy(position: str) -> tuple[str, str]:
    return {
        "top-left": ("40", "40"),
        "top-center": ("(W-w)/2", "40"),
        "top-right": ("W-w-40", "40"),
        "middle-left": ("40", "(H-h)/2"),
        "center": ("(W-w)/2", "(H-h)/2"),
        "middle-right": ("W-w-40", "(H-h)/2"),
        "bottom-left": ("40", "H-h-40"),
        "bottom-center": ("(W-w)/2", "H-h-40"),
        "bottom-right": ("W-w-40", "H-h-40"),
    }.get(position, ("W-w-40", "40"))


def _filter_complex(
    portrait: bool,
    background: str,
    use_ass: bool,
    logo: Path | None,
    logo_opacity: float,
    logo_position: str = "top-right",
    ass_file: str = "captions.ass",
) -> str:
    chain = _portrait_chain(background) if portrait else (
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black"
    )
    graph = f"[0:v]{chain}"
    if use_ass:
        graph += f",ass={ass_file}"
    if logo is not None:
        x, y = _logo_xy(logo_position)
        graph += "[base];[1:v]scale=200:-2,format=rgba,colorchannelmixer=aa={:.2f}[logo];[base][logo]overlay={}:{}[v]".format(
            max(0.0, min(1.0, logo_opacity)), x, y
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
    caption_font: str = "Arial Black",
    caption_bold: bool = True,
    hook_style: str = "classic",
    watermark_position: str = "top-right",
    credit_position: str = "bottom-center",
    credit_opacity: float = 1.0,
    translations: list[str] | None = None,
    on_progress=None,
    on_log=None,
) -> Path:
    if not ffmpeg:
        raise RuntimeError("ffmpeg was not found. Put ffmpeg.exe in assets/ffmpeg or install it on PATH.")
    in_abs = input_path.resolve()
    out_abs = output_path.resolve()
    out_abs.parent.mkdir(parents=True, exist_ok=True)
    workdir = out_abs.parent
    ass_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", out_abs.stem).strip("._") or "captions"
    ass_name = f"{ass_stem}.ass"
    use_ass = bool((captions and words) or (hook and hook_text.strip()) or credit.strip())
    if use_ass:
        (workdir / ass_name).write_text(
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
                caption_font=caption_font,
                caption_bold=caption_bold,
                hook_style=hook_style,
                credit_position=credit_position,
                credit_opacity=credit_opacity,
                translations=translations,
            ),
            encoding="utf-8",
        )

    logo = Path(watermark).resolve() if watermark and logo_opacity > 0 and Path(watermark).is_file() else None
    if watermark and logo_opacity > 0 and logo is None and on_log:
        on_log("Watermark file not found, skipping logo")

    graph = _filter_complex(portrait, background, use_ass, logo, logo_opacity, watermark_position, ass_file=ass_name)
    base_cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(in_abs),
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
        str(out_abs),
    ]

    hardware = detect_encoder(ffmpeg)
    with _ENCODER_LOCK:
        probe_errors = {enc: msg for (bin_path, enc), msg in _PROBE_ERRORS.items() if bin_path == ffmpeg}
        hw_failed = bool(hardware and _ENCODER_STATUS.get(hardware) is False)
    if hardware is None and on_log and probe_errors:
        detail = "; ".join(f"{name}: {error}" for name, error in probe_errors.items())
        on_log(f"Hardware encoder tidak tersedia ({detail}); memakai libx264")
    if hw_failed:
        hardware = None
    attempts: list[tuple[str, list[str]]] = []
    for name, args in _HW_ENCODERS:
        if name == hardware:
            attempts.append((name, args))
            break
    attempts.append(("libx264", _CPU_ARGS))

    last_error = ""
    for name, video_args in attempts:
        cmd = base_cmd[:-1] + video_args + [str(out_abs)]
        if on_log:
            on_log(f"Rendering with {name}")
        if out_abs.exists():
            out_abs.unlink()
        process = subprocess.Popen(
            cmd,
            cwd=str(workdir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=_CREATE_NO_WINDOW,
        )
        tail: list[str] = []
        timed_out = threading.Event()

        def _kill_on_timeout(proc=process, flag=timed_out) -> None:
            flag.set()
            proc.kill()

        watchdog = threading.Timer(1800, _kill_on_timeout)
        watchdog.daemon = True
        watchdog.start()
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
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            timed_out.set()
        finally:
            watchdog.cancel()
            if process.stdout:
                process.stdout.close()
        if timed_out.is_set():
            last_error = "ffmpeg timed out"
            with _ENCODER_LOCK:
                _ENCODER_STATUS[name] = False
            if on_log:
                on_log(f"{name} timed out, trying fallback")
            continue
        if process.returncode == 0 and out_abs.exists() and out_abs.stat().st_size > 1000:
            with _ENCODER_LOCK:
                _ENCODER_STATUS[name] = True
            if on_progress:
                on_progress(100.0)
            return output_path
        last_error = "\n".join(tail[-8:]) or f"ffmpeg exited with {process.returncode}"
        with _ENCODER_LOCK:
            _ENCODER_STATUS[name] = False
        if on_log:
            on_log(f"{name} failed, trying fallback")
    raise RuntimeError(f"ffmpeg failed: {last_error}")


def probe_size(path: Path, ffmpeg: str) -> tuple[int, int] | None:
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)],
        capture_output=True,
        timeout=30,
        creationflags=_CREATE_NO_WINDOW,
    )
    match = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", proc.stderr.decode("utf-8", "replace"))
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))
