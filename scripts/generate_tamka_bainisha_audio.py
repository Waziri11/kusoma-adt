#!/usr/bin/env python3
"""Generate cache-safe RehemaNeural audio for Tamka / bainisha corrections."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import tempfile
from pathlib import Path

import edge_tts

from apply_tamka_bainisha_slash import TARGET_BASE_IDS


ROOT = Path(__file__).resolve().parents[1]
LANG = ROOT / "content" / "i18n" / "sw-TZ"
VOICE = "sw-TZ-RehemaNeural"
SUFFIX = "slash_v42"


def spoken_text(value: str) -> str:
    return value.replace(" / ", " au ").strip()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--retries", type=int, default=6)
    args = parser.parse_args()

    texts = json.loads((LANG / "texts.json").read_text(encoding="utf-8"))
    audios = json.loads((LANG / "audios.json").read_text(encoding="utf-8"))
    target_ids = [
        text_id
        for base_id in sorted(TARGET_BASE_IDS)
        for text_id in (base_id, f"{base_id}_easy_read")
    ]
    items = []
    for text_id in target_ids:
        visible = texts.get(text_id)
        if not isinstance(visible, str) or " / bainisha" not in visible:
            raise RuntimeError(f"{text_id}: missing approved visible slash text")
        items.append((text_id, spoken_text(visible)))

    unique_spoken = sorted({spoken for _, spoken in items})
    semaphore = asyncio.Semaphore(args.concurrency)
    with tempfile.TemporaryDirectory(prefix="kusoma-tamka-slash-v42-") as temp_name:
        temp = Path(temp_name)
        generated = {
            spoken: temp / f"spoken-{index:03d}.mp3"
            for index, spoken in enumerate(unique_spoken)
        }

        async def synthesize(spoken: str, destination: Path) -> None:
            last_error: Exception | None = None
            for attempt in range(1, args.retries + 1):
                try:
                    async with semaphore:
                        await edge_tts.Communicate(spoken, VOICE).save(str(destination))
                    if not destination.is_file() or destination.stat().st_size == 0:
                        raise RuntimeError("generated an empty MP3")
                    return
                except Exception as error:
                    last_error = error
                    destination.unlink(missing_ok=True)
                    if attempt < args.retries:
                        await asyncio.sleep(min(2 ** (attempt - 1), 20))
            raise RuntimeError(f"TTS failed after {args.retries} attempts: {spoken!r}") from last_error

        await asyncio.gather(
            *(synthesize(spoken, destination) for spoken, destination in generated.items())
        )
        audio_dir = LANG / "audio"
        for text_id, spoken in items:
            filename = f"{text_id}_{SUFFIX}.mp3"
            shutil.copyfile(generated[spoken], audio_dir / filename)
            audios[text_id] = filename

    (LANG / "audios.json").write_text(
        json.dumps(audios, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Generated {len(items)} fresh {VOICE} recordings from "
        f"{len(unique_spoken)} unique spoken sentences; slash narrated as 'au'."
    )


if __name__ == "__main__":
    asyncio.run(main())
