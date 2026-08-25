#!/usr/bin/env python3
"""Regenerate the page 27-28 fill-in-the-blank readings with RehemaNeural."""

import asyncio
import json
from pathlib import Path

import edge_tts


ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "content" / "i18n" / "sw-TZ"
VOICE = "sw-TZ-RehemaNeural"
TEXT_IDS = (
    "pg027_n0100",
    "pg027_n0102",
    "pg028_n0004",
    "pg028_n0007",
    "pg028_n0010",
    "pg028_n0013",
    "pg028_n0016",
    "pg028_n0019",
    "pg028_n0022",
    "pg028_n0025",
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
    print(f"Updated {len(TEXT_IDS)} fill-in-the-blank readings with {VOICE}.")


if __name__ == "__main__":
    asyncio.run(main())
