#!/usr/bin/env python3
"""Regenerate page 62 numbered readings with spoken Swahili numbers."""

import asyncio
import json
import re
from pathlib import Path

import edge_tts


ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "content" / "i18n" / "sw-TZ"
VOICE = "sw-TZ-RehemaNeural"
TEXT_IDS = (
    "pg062_n0002",
    "pg062_n0003",
    "pg062_n0007",
    "pg062_n0008",
    "pg062_n0015",
    "pg062_n0016",
    "pg062_n0002_easy_read",
    "pg062_n0003_easy_read",
    "pg062_n0015_easy_read",
    "pg062_n0016_easy_read",
)
NUMBER_WORDS = {"1": "moja", "2": "mbili", "3": "tatu"}


def spoken_text(text: str) -> str:
    return re.sub(r"\b([123])\b", lambda match: NUMBER_WORDS[match.group(1)], text)


async def main() -> None:
    texts = json.loads((I18N / "texts.json").read_text(encoding="utf-8"))
    audios = json.loads((I18N / "audios.json").read_text(encoding="utf-8"))
    await asyncio.gather(
        *(
            edge_tts.Communicate(spoken_text(texts[text_id]), VOICE).save(
                str(I18N / "audio" / audios[text_id])
            )
            for text_id in TEXT_IDS
        )
    )
    print(f"Updated {len(TEXT_IDS)} page 62 readings with spoken Swahili numbers.")


if __name__ == "__main__":
    asyncio.run(main())
