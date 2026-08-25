#!/usr/bin/env python3
"""Rebuild every mapped, non-empty Swahili narration with RehemaNeural."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import tempfile
from pathlib import Path

import edge_tts


ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "content" / "i18n" / "sw-TZ"
VOICE = "sw-TZ-RehemaNeural"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--retries", type=int, default=6)
    parser.add_argument(
        "--ids",
        default="",
        help="Optional comma-separated text IDs to rebuild; defaults to every mapping.",
    )
    args = parser.parse_args()

    texts = json.loads((I18N / "texts.json").read_text(encoding="utf-8"))
    audios = json.loads((I18N / "audios.json").read_text(encoding="utf-8"))
    requested_ids = {value.strip() for value in args.ids.split(",") if value.strip()}
    items = [
        (text_id, text.strip(), filename)
        for text_id, filename in audios.items()
        if isinstance((text := texts.get(text_id)), str) and text.strip()
        and (not requested_ids or text_id in requested_ids)
    ]
    missing_ids = requested_ids - {text_id for text_id, _, _ in items}
    if missing_ids:
        raise SystemExit(f"Unknown, unmapped, or empty text IDs: {sorted(missing_ids)}")
    unique_texts = sorted({text for _, text, _ in items})
    semaphore = asyncio.Semaphore(args.concurrency)

    with tempfile.TemporaryDirectory(prefix="kusoma-rehema-") as temp_name:
        temp = Path(temp_name)
        generated = {
            text: temp / f"rehema-{index:05d}.mp3"
            for index, text in enumerate(unique_texts)
        }

        async def synthesize(text: str, destination: Path) -> None:
            last_error: Exception | None = None
            for attempt in range(1, args.retries + 1):
                try:
                    async with semaphore:
                        await edge_tts.Communicate(text, VOICE).save(str(destination))
                    return
                except Exception as error:  # network service can reset long batches
                    last_error = error
                    destination.unlink(missing_ok=True)
                    if attempt < args.retries:
                        await asyncio.sleep(min(2 ** (attempt - 1), 20))
            raise RuntimeError(
                f"Failed after {args.retries} attempts: {text[:80]!r}"
            ) from last_error

        await asyncio.gather(
            *(synthesize(text, destination) for text, destination in generated.items())
        )

        audio_dir = I18N / "audio"
        for _, text, filename in items:
            shutil.copyfile(generated[text], audio_dir / filename)

    print(
        f"Rebuilt {len(items)} mapped files from {len(unique_texts)} unique texts "
        f"with {VOICE}."
    )


if __name__ == "__main__":
    asyncio.run(main())
