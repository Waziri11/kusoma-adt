#!/usr/bin/env python3
"""Generate cache-safe RehemaNeural audio for the additional feedback IDs."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import tempfile
from pathlib import Path

import edge_tts

from apply_additional_feedback import CHANGED_BASE_IDS


ROOT = Path(__file__).resolve().parents[1]
LANG_DIR = ROOT / "content" / "i18n" / "sw-TZ"
VOICE = "sw-TZ-RehemaNeural"
SUFFIX = "feedback_v28"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--retries", type=int, default=6)
    parser.add_argument(
        "--base-id",
        action="append",
        help="Regenerate only this stable base ID (repeatable).",
    )
    args = parser.parse_args()

    texts = json.loads((LANG_DIR / "texts.json").read_text(encoding="utf-8"))
    audios = json.loads((LANG_DIR / "audios.json").read_text(encoding="utf-8"))
    target_ids: list[str] = []
    selected_ids = set(args.base_id or CHANGED_BASE_IDS)
    unknown = selected_ids - CHANGED_BASE_IDS
    if unknown:
        raise RuntimeError(f"Unknown correction IDs: {sorted(unknown)}")
    for base_id in sorted(selected_ids):
        for text_id in (base_id, f"{base_id}_easy_read"):
            if isinstance(texts.get(text_id), str) and texts[text_id].strip():
                target_ids.append(text_id)

    semaphore = asyncio.Semaphore(args.concurrency)
    with tempfile.TemporaryDirectory(prefix="kusoma-feedback-v28-") as temp_name:
        temp = Path(temp_name)

        async def synthesize(text_id: str) -> tuple[str, Path]:
            destination = temp / f"{text_id}_{SUFFIX}.mp3"
            last_error: Exception | None = None
            for attempt in range(1, args.retries + 1):
                try:
                    async with semaphore:
                        await edge_tts.Communicate(texts[text_id].strip(), VOICE).save(
                            str(destination)
                        )
                    if destination.stat().st_size == 0:
                        raise RuntimeError("generated an empty MP3")
                    return text_id, destination
                except Exception as error:
                    last_error = error
                    destination.unlink(missing_ok=True)
                    if attempt < args.retries:
                        await asyncio.sleep(min(2 ** (attempt - 1), 20))
            raise RuntimeError(f"{text_id}: TTS failed after {args.retries} attempts") from last_error

        generated = await asyncio.gather(*(synthesize(text_id) for text_id in target_ids))
        audio_dir = LANG_DIR / "audio"
        for text_id, staged in generated:
            filename = staged.name
            shutil.copyfile(staged, audio_dir / filename)
            audios[text_id] = filename

    (LANG_DIR / "audios.json").write_text(
        json.dumps(audios, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {len(target_ids)} fresh {VOICE} recordings with suffix {SUFFIX}.")


if __name__ == "__main__":
    asyncio.run(main())
