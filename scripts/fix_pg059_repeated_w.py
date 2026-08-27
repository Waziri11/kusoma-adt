#!/usr/bin/env python3
"""Remove the lower repeated w on page 59 and update its narration."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import edge_tts


ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "content" / "i18n" / "sw-TZ"
TEXT_ID = "pg059_im008_crop_v1"
VISIBLE_TEXT = "Herufi u, w, m, w, a, m na n"
SPOKEN_TEXT = "Herufi. u. wa. ma. wa. a. ma. na. na."
FILENAME = "pg059_im008_crop_v1_without_lower_w_v23.mp3"
VOICE = "sw-TZ-RehemaNeural"


def build_image() -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(ROOT / "images" / "pg059_im008_crop_v1.png"),
            "-vf",
            "drawbox=x=30:y=175:w=125:h=125:color=white:t=fill",
            "-frames:v",
            "1",
            str(ROOT / "images" / "pg059_im008_crop_v2.png"),
        ],
        check=True,
    )


async def synthesize(destination: Path) -> None:
    last_error: Exception | None = None
    for attempt in range(1, 7):
        try:
            await edge_tts.Communicate(
                SPOKEN_TEXT, VOICE, rate="-8%"
            ).save(str(destination))
            if destination.stat().st_size > 0:
                return
        except Exception as error:  # pragma: no cover - network dependent
            last_error = error
        destination.unlink(missing_ok=True)
        await asyncio.sleep(attempt * 1.5)
    raise RuntimeError("TTS generation failed after six attempts") from last_error


def validate_audio(path: Path) -> None:
    duration = float(
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
    maximum = re.search(r"max_volume:\s*(-?[0-9.]+) dB", result.stderr)
    if not 1.0 <= duration <= 20.0 or not maximum or float(maximum.group(1)) <= -45:
        raise RuntimeError("Generated page 59 narration is invalid or silent")


async def main() -> None:
    build_image()
    with tempfile.TemporaryDirectory(prefix="kusoma-pg059-w-") as name:
        staged = Path(name) / FILENAME
        await synthesize(staged)
        validate_audio(staged)
        shutil.copyfile(staged, I18N / "audio" / FILENAME)

    texts_path = I18N / "texts.json"
    audios_path = I18N / "audios.json"
    texts = json.loads(texts_path.read_text(encoding="utf-8"))
    audios = json.loads(audios_path.read_text(encoding="utf-8"))
    texts[TEXT_ID] = VISIBLE_TEXT
    audios[TEXT_ID] = FILENAME
    texts_path.write_text(
        json.dumps(texts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    audios_path.write_text(
        json.dumps(audios, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    html_path = ROOT / "pg059_sec001.html"
    html = html_path.read_text(encoding="utf-8")
    html = html.replace(
        'src="images/pg059_im008_crop_v1.png"',
        'src="images/pg059_im008_crop_v2.png"',
    )
    html_path.write_text(html, encoding="utf-8")
    print(f"Updated {TEXT_ID}: {VISIBLE_TEXT}")


if __name__ == "__main__":
    asyncio.run(main())
