# Third-party notices

The Windows release package (`AIKLIPYT-v1.0.0-win64.zip`) bundles these
executables so the app works without separate downloads:

## FFmpeg 8.0.1-full_build (gyan.dev)

- Path: `assets/ffmpeg/ffmpeg.exe`
- Project: https://ffmpeg.org/
- Build: https://www.gyan.dev/ffmpeg/builds/
- License: GNU General Public License v3 (the "full" build includes GPL
  components). License text: `licenses/GPL-3.0.txt`.
- Corresponding source: https://www.gyan.dev/ffmpeg/builds/#git-master-builds
  and https://ffmpeg.org/download.html
- FFmpeg is a trademark of Fabrice Bellard, originator of the FFmpeg project.
  This project is not affiliated with or endorsed by the FFmpeg project.

## Deno 2.8.1

- Path: `bin/deno.exe`
- Project: https://github.com/denoland/deno
- License: MIT. Copyright 2018-2026 the Deno authors.
  License text: `licenses/MIT-Deno.txt`.

## Python packages

`yt-dlp` is installed into a local virtual environment by `run.bat` on first
launch. It is not bundled in the ZIP. yt-dlp is released under the Unlicense:
https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE

AIKLIPYT itself is an independent clean-room implementation and is not
affiliated with the original YT Short Clipper project.
