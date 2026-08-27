#!/usr/bin/env python3
"""Regenerate page 104 question 2-4 narration with spoken dashes."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import edge_tts


ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "content" / "i18n" / "sw-TZ"
AUDIO_DIR = I18N / "audio"
VOICE = "sw-TZ-RehemaNeural"
OUTPUT_SUFFIX = "dashi_v21"

SPOKEN_TEXTS = {
    "pg104_n0023": (
        "Albino ana haki ya kupendwa, dashi, na dashi."
    ),
    "pg104_n0023_easy_read": (
        "Mtu mwenye ualbino ana haki ya kupendwa, dashi, na dashi."
    ),
    "pg104_n0025": (
        "Kuna ulemavu wa kutoona, dashi, dashi, na ulemavu wa akili."
    ),
    "pg104_n0025_easy_read": (
        "Kuna ulemavu wa kutoona, dashi, dashi, na ulemavu wa akili."
    ),
    "pg104_n0027": (
        "Walemavu wakipendwa na kuthaminiwa wanaweza dashi."
    ),
    "pg104_n0027_easy_read": (
        "Watu wenye ulemavu wakipendwa na kuthaminiwa, wanaweza dashi."
    ),
}


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


async def synthesize(text_id: str, spoken_text: str, destination: Path) -> None:
    await edge_tts.Communicate(spoken_text, VOICE).save(str(destination))
    duration = probe_duration(destination)
    if destination.stat().st_size <= 0 or duration <= 1.0:
        raise RuntimeError(
            f"Invalid generated audio for {text_id}: {duration:.3f} seconds"
        )


async def main() -> None:
    audios_path = I18N / "audios.json"
    audios = json.loads(audios_path.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory(prefix="kusoma-pg104-dashes-") as name:
        staging = Path(name)
        jobs = []
        outputs: dict[str, tuple[str, Path]] = {}

        for text_id, spoken_text in SPOKEN_TEXTS.items():
            filename = f"{text_id}_{OUTPUT_SUFFIX}.mp3"
            staged = staging / filename
            outputs[text_id] = (filename, staged)
            jobs.append(synthesize(text_id, spoken_text, staged))

        await asyncio.gather(*jobs)

        for text_id, (filename, staged) in outputs.items():
            shutil.copyfile(staged, AUDIO_DIR / filename)
            audios[text_id] = filename

    audios_path.write_text(
        json.dumps(audios, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Generated {len(SPOKEN_TEXTS)} page 104 recordings with {VOICE}; "
        "every visible answer line is spoken as dashi."
    )


if __name__ == "__main__":
    asyncio.run(main())
