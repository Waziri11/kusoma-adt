#!/usr/bin/env python3
"""Regenerate every numbered exercise heading with Swahili ordinal wording."""

import asyncio
import json
import re
import shutil
import tempfile
from pathlib import Path

import edge_tts


ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "content" / "i18n" / "sw-TZ"
VOICE = "sw-TZ-RehemaNeural"
FILENAME_SUFFIX = "ordinal_v9"
ORDINALS = {
    1: "kwanza",
    2: "pili",
    3: "tatu",
    4: "nne",
    5: "tano",
    6: "sita",
    7: "saba",
}
EXERCISE_HEADING = re.compile(r"^Zoezi la ([1-7])$", re.IGNORECASE)


async def synthesize_with_retries(text: str, destination: Path) -> None:
    last_error = None
    for attempt in range(1, 7):
        try:
            await edge_tts.Communicate(text, VOICE).save(str(destination))
            if destination.stat().st_size <= 0:
                raise RuntimeError("generated file is empty")
            return
        except Exception as error:
            last_error = error
            if destination.exists():
                destination.unlink()
            if attempt < 6:
                await asyncio.sleep(attempt * 1.5)
    raise RuntimeError(f"Could not synthesize {text!r}: {last_error}")


async def main() -> None:
    texts_path = I18N / "texts.json"
    audios_path = I18N / "audios.json"
    texts = json.loads(texts_path.read_text(encoding="utf-8"))
    audios = json.loads(audios_path.read_text(encoding="utf-8"))

    targets = {}
    for text_id, displayed_text in texts.items():
        if not isinstance(displayed_text, str) or text_id not in audios:
            continue
        match = EXERCISE_HEADING.fullmatch(displayed_text.strip())
        if match:
            number = int(match.group(1))
            targets[text_id] = f"Zoezi la {ORDINALS[number]}"

    if not targets:
        raise RuntimeError("No numbered exercise-heading audio mappings found")

    unique_readings = sorted(set(targets.values()))
    with tempfile.TemporaryDirectory(prefix="kusoma-exercise-ordinals-") as temp_dir:
        staging = Path(temp_dir)
        generated = {
            reading: staging / f"reading-{index:02d}.mp3"
            for index, reading in enumerate(unique_readings, start=1)
        }
        await asyncio.gather(
            *(synthesize_with_retries(reading, path) for reading, path in generated.items())
        )

        new_mappings = dict(audios)
        audio_dir = I18N / "audio"
        staged_targets = []
        for text_id, reading in targets.items():
            old_filename = Path(audios[text_id])
            new_filename = f"{old_filename.stem}_{FILENAME_SUFFIX}.mp3"
            staged_file = staging / new_filename
            shutil.copyfile(generated[reading], staged_file)
            staged_targets.append((staged_file, audio_dir / new_filename))
            new_mappings[text_id] = new_filename

        for staged_file, destination in staged_targets:
            shutil.copyfile(staged_file, destination)
        audios_path.write_text(
            json.dumps(new_mappings, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    normal = sum(not text_id.endswith("_easy_read") for text_id in targets)
    easy_read = len(targets) - normal
    print(
        f"Updated {len(targets)} exercise headings "
        f"({normal} normal, {easy_read} easy-read) using "
        f"{len(unique_readings)} ordinal readings."
    )


if __name__ == "__main__":
    asyncio.run(main())
