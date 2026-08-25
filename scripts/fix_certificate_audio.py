#!/usr/bin/env python3
"""Regenerate the certificate heading and number with clear Swahili speech."""

import asyncio
import json
from pathlib import Path

import edge_tts


ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "content" / "i18n" / "sw-TZ"
VOICE = "sw-TZ-RehemaNeural"
TEXT_IDS = (
    "pg001_n0011",
    "pg001_n0012",
    "pg001_n0011_easy_read",
    "pg001_n0012_easy_read",
)


async def main() -> None:
    texts = json.loads((I18N / "texts.json").read_text(encoding="utf-8"))
    audios = json.loads((I18N / "audios.json").read_text(encoding="utf-8"))
    await asyncio.gather(
        *(
            edge_tts.Communicate(texts[text_id], VOICE).save(
                str(I18N / "audio" / audios[text_id])
            )
            for text_id in TEXT_IDS
        )
    )
    print(f"Updated {len(TEXT_IDS)} certificate readings with {VOICE}.")


if __name__ == "__main__":
    asyncio.run(main())
