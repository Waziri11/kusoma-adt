#!/usr/bin/env python3
"""Build complete page-102 question narration with spoken blank markers."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import edge_tts


ROOT = Path(__file__).resolve().parents[1]
AUDIO_DIR = ROOT / "content" / "i18n" / "sw-TZ" / "audio"
VOICE = "sw-TZ-RehemaNeural"

SPOKEN_QUESTIONS = {
    "pg102_n0009": "Moja. Wanafunzi walikwenda dashi.",
    "pg102_n0011": "Mbili. Walipokuwa njiani, wanafunzi walifanya dashi.",
    "pg102_n0013": "Tatu. Mbuga ya dashi ina wanyama mbalimbali.",
    "pg102_n0015": "Nne. Wanafunzi walipigwa dashi walipokuwa mbugani.",
    "pg102_n0017": "Tano. Baada ya safari, walirudi dashi.",
}


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="kusoma-pg102-questions-") as temp_name:
        temp_dir = Path(temp_name)

        async def synthesize(text_id: str, spoken_text: str) -> None:
            staged = temp_dir / f"{text_id}.mp3"
            await edge_tts.Communicate(spoken_text, VOICE).save(str(staged))
            staged.replace(AUDIO_DIR / f"{text_id}_questions_v20.mp3")

        await asyncio.gather(
            *(synthesize(text_id, spoken) for text_id, spoken in SPOKEN_QUESTIONS.items())
        )

    print(f"Built {len(SPOKEN_QUESTIONS)} page-102 question clips with {VOICE}.")


if __name__ == "__main__":
    asyncio.run(main())
