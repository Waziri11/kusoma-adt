#!/usr/bin/env python3
"""Generate clear page 55 image-name narration with RehemaNeural."""

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
AUDIO_DIR = I18N / "audio"
VOICE = "sw-TZ-RehemaNeural"
SUFFIX = "name_v23"

TARGETS = {
    "pg055_im002": "Redio.",
    "pg055_im004": "Bata.",
    "pg055_im001": "Rula.",
    "pg055_im003": "Redio.",
}


def verify_narration_proxies() -> None:
    """Ensure image names remain in read-aloud when image descriptions are off."""
    html = (ROOT / "pg055_sec001.html").read_text(encoding="utf-8")
    for text_id in TARGETS:
        if re.search(rf"<img[^>]+data-id=[\"']{text_id}[\"']", html):
            raise RuntimeError(
                f"{text_id} is still attached to an image and can be skipped"
            )
        if not re.search(
            rf"<span[^>]+data-id=[\"']{text_id}[\"'][^>]+aria-hidden=[\"']true[\"']",
            html,
        ):
            raise RuntimeError(f"Missing read-aloud proxy for {text_id}")


def probe(path: Path) -> tuple[float, float, float]:
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
    mean_match = re.search(r"mean_volume:\s*(-?[0-9.]+) dB", result.stderr)
    max_match = re.search(r"max_volume:\s*(-?[0-9.]+) dB", result.stderr)
    if not mean_match or not max_match:
        raise RuntimeError(f"Could not validate the audio signal for {path.name}")
    return duration, float(mean_match.group(1)), float(max_match.group(1))


async def synthesize(text: str, destination: Path) -> None:
    last_error: Exception | None = None
    for attempt in range(1, 7):
        try:
            await edge_tts.Communicate(text, VOICE, rate="-8%").save(
                str(destination)
            )
            if destination.stat().st_size > 0:
                return
        except Exception as error:  # pragma: no cover - network dependent
            last_error = error
        destination.unlink(missing_ok=True)
        await asyncio.sleep(attempt * 1.5)
    raise RuntimeError("TTS generation failed after six attempts") from last_error


async def main() -> None:
    verify_narration_proxies()
    audios_path = I18N / "audios.json"
    audios = json.loads(audios_path.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory(prefix="kusoma-pg055-images-") as name:
        staged = {
            text_id: Path(name) / f"{text_id}_{SUFFIX}.mp3"
            for text_id in TARGETS
        }
        await asyncio.gather(
            *(
                synthesize(TARGETS[text_id], path)
                for text_id, path in staged.items()
            )
        )

        measurements: dict[str, tuple[float, float, float]] = {}
        for text_id, path in staged.items():
            duration, mean_volume, max_volume = probe(path)
            if not 0.20 <= duration <= 12.0:
                raise RuntimeError(
                    f"Unexpected duration for {text_id}: {duration:.3f} seconds"
                )
            if mean_volume <= -55.0 or max_volume <= -45.0:
                raise RuntimeError(
                    f"{text_id} is effectively silent: mean {mean_volume:.1f} dB, "
                    f"max {max_volume:.1f} dB"
                )
            measurements[text_id] = (duration, mean_volume, max_volume)

        for text_id, path in staged.items():
            filename = path.name
            shutil.copyfile(path, AUDIO_DIR / filename)
            audios[text_id] = filename

    audios_path.write_text(
        json.dumps(audios, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for text_id, (duration, mean_volume, max_volume) in measurements.items():
        print(
            f"{text_id}: {duration:.3f} seconds, "
            f"mean {mean_volume:.1f} dB, max {max_volume:.1f} dB"
        )


if __name__ == "__main__":
    asyncio.run(main())
