#!/usr/bin/env python3
"""Generate the page 49 Z-image read-aloud clip as the sound "Zah"."""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import edge_tts


ROOT = Path(__file__).resolve().parents[1]
AUDIO_DIR = ROOT / "content" / "i18n" / "sw-TZ" / "audio"
VOICE = "sw-TZ-RehemaNeural"
SPOKEN_TEXT = "Zah."
OUTPUT_NAME = "pg049_im003_crop_v1_crop1_zah_v23.mp3"


def probe_duration(path: Path) -> float:
    return float(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                str(path),
            ],
            text=True,
        ).strip()
    )


def probe_volume(path: Path) -> tuple[float, float]:
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(path),
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    mean_match = re.search(r"mean_volume:\s*(-?[0-9.]+) dB", result.stderr)
    max_match = re.search(r"max_volume:\s*(-?[0-9.]+) dB", result.stderr)
    if not mean_match or not max_match:
        raise RuntimeError("Could not validate the generated clip's audio signal")
    return float(mean_match.group(1)), float(max_match.group(1))


async def synthesize(destination: Path) -> None:
    last_error: Exception | None = None
    for attempt in range(1, 7):
        try:
            await edge_tts.Communicate(SPOKEN_TEXT, VOICE, rate="-8%").save(
                str(destination)
            )
            if destination.stat().st_size > 0:
                return
        except Exception as error:  # pragma: no cover - network dependent
            last_error = error
        await asyncio.sleep(attempt * 1.5)
    raise RuntimeError("TTS generation failed after six attempts") from last_error


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="kusoma-pg049-zah-") as name:
        staged = Path(name) / OUTPUT_NAME
        await synthesize(staged)
        duration = probe_duration(staged)
        mean_volume, max_volume = probe_volume(staged)
        if not 0.20 <= duration <= 3.00:
            raise RuntimeError(f"Unexpected clip duration: {duration:.3f} seconds")
        if mean_volume <= -55.0 or max_volume <= -45.0:
            raise RuntimeError(
                "Generated clip is effectively silent: "
                f"mean {mean_volume:.1f} dB, max {max_volume:.1f} dB"
            )
        shutil.copyfile(staged, AUDIO_DIR / OUTPUT_NAME)

    print(
        f"Generated {OUTPUT_NAME}: {duration:.3f} seconds, "
        f"mean {mean_volume:.1f} dB, max {max_volume:.1f} dB"
    )


if __name__ == "__main__":
    asyncio.run(main())
