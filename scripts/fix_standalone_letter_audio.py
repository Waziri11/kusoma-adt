#!/usr/bin/env python3
"""Regenerate every mapped standalone letter with a clear Kiswahili reading."""

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
VOICE = "sw-TZ-RehemaNeural"
SUFFIX = "clear_letter_v11"
LETTER_READINGS = {
    "a": "a", "b": "ba", "c": "cha", "d": "da", "e": "e",
    "f": "fa", "g": "ga", "h": "ha", "i": "i", "j": "ja",
    "k": "ka", "l": "la", "m": "ma", "n": "na", "o": "o",
    "p": "pa", "q": "kwa", "r": "ra", "s": "sa", "t": "ta",
    "u": "u", "v": "va", "w": "wa", "x": "ksa", "y": "ya",
    "z": "za",
}


async def synthesize(reading: str, destination: Path) -> None:
    last_error = None
    for attempt in range(1, 7):
        try:
            phrase = f"Herufi {reading}."
            raw = destination.with_suffix(".raw.mp3")
            await asyncio.wait_for(
                edge_tts.Communicate(phrase, VOICE, rate="-10%").save(str(raw)),
                timeout=30,
            )
            total = float(subprocess.check_output(
                [
                    "ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=nw=1:nk=1", str(raw),
                ], text=True,
            ).strip())
            start = 0.0
            duration = total
            subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", f"{start:.4f}", "-t", f"{duration:.4f}",
                    "-i", str(raw),
                    "-af", "adelay=80:all=1,apad=pad_dur=0.18,volume=1.12,alimiter=limit=0.90",
                    "-ar", "44100", "-b:a", "128k", str(destination),
                ],
                check=True,
            )
            raw.unlink(missing_ok=True)
            if destination.stat().st_size <= 0:
                raise RuntimeError("generated file is empty")
            return
        except Exception as error:
            last_error = error
            destination.unlink(missing_ok=True)
            destination.with_suffix(".raw.mp3").unlink(missing_ok=True)
            if attempt < 6:
                await asyncio.sleep(attempt * 1.5)
    raise RuntimeError(f"Could not synthesize {reading!r}: {last_error}")


async def main() -> None:
    texts_path = I18N / "texts.json"
    audios_path = I18N / "audios.json"
    texts = json.loads(texts_path.read_text(encoding="utf-8"))
    audios = json.loads(audios_path.read_text(encoding="utf-8"))
    targets = {
        text_id: LETTER_READINGS[displayed_text.strip().lower()]
        for text_id, displayed_text in texts.items()
        if text_id in audios
        and isinstance(displayed_text, str)
        and re.fullmatch(r"[A-Za-z]", displayed_text.strip())
    }
    if not targets:
        raise RuntimeError("No mapped standalone letters found")

    with tempfile.TemporaryDirectory(prefix="kusoma-standalone-letters-") as temp_name:
        temp = Path(temp_name)
        generated = {
            reading: temp / f"{reading}.mp3"
            for reading in sorted(set(targets.values()))
        }
        await asyncio.gather(
            *(synthesize(reading, path) for reading, path in generated.items())
        )

        audio_dir = I18N / "audio"
        for text_id, reading in targets.items():
            filename = f"{text_id}_{SUFFIX}.mp3"
            shutil.copyfile(generated[reading], audio_dir / filename)
            audios[text_id] = filename

    audios_path.write_text(
        json.dumps(audios, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    normal = sum(not text_id.endswith("_easy_read") for text_id in targets)
    print(
        f"Updated {len(targets)} standalone letter recordings "
        f"({normal} normal, {len(targets) - normal} easy-read) with {VOICE}."
    )


if __name__ == "__main__":
    asyncio.run(main())
