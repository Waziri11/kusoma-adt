#!/usr/bin/env python3
"""Regenerate only the ISBN readings, speaking digits in Kiswahili."""

import asyncio
import json
from pathlib import Path

import edge_tts


ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "content" / "i18n" / "sw-TZ"
VOICE = "sw-TZ-RehemaNeural"
TEXT_IDS = ("pg001_n0016", "pg001_n0016_easy_read")
SPOKEN_TEXT = (
    "ISBN: tisa saba nane, tisa tisa nane saba, sifuri tisa, "
    "nne nne sita, mbili"
)


async def main() -> None:
    audios = json.loads((I18N / "audios.json").read_text(encoding="utf-8"))
    await asyncio.gather(
        *(
            edge_tts.Communicate(SPOKEN_TEXT, VOICE).save(
                str(I18N / "audio" / audios[text_id])
            )
            for text_id in TEXT_IDS
        )
    )
    print(f"Updated {len(TEXT_IDS)} ISBN readings with Kiswahili digits.")


if __name__ == "__main__":
    asyncio.run(main())
