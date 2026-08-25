#!/usr/bin/env python3
"""Regenerate digit-bearing educational audio with explicit Swahili number words."""

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

CARDINALS = {
    0: "sifuri",
    1: "moja",
    2: "mbili",
    3: "tatu",
    4: "nne",
    5: "tano",
    6: "sita",
    7: "saba",
    8: "nane",
    9: "tisa",
    10: "kumi",
    20: "ishirini",
    30: "thelathini",
    40: "arobaini",
    50: "hamsini",
    60: "sitini",
    70: "sabini",
    80: "themanini",
    90: "tisini",
}

ORDINALS = {
    1: "kwanza",
    2: "pili",
    3: "tatu",
    4: "nne",
    5: "tano",
    6: "sita",
    7: "saba",
    8: "nane",
    9: "tisa",
}


def cardinal(number: int) -> str:
    if number in CARDINALS:
        return CARDINALS[number]
    if 10 < number < 100:
        tens, ones = divmod(number, 10)
        return f"{CARDINALS[tens * 10]} na {CARDINALS[ones]}"
    raise ValueError(f"Unsupported educational number: {number}")


def is_target(text: str) -> bool:
    value = text.strip()
    return bool(
        re.fullmatch(r"\d+\.?", value)
        or re.search(r"\bZoezi la \d+\b", value, re.IGNORECASE)
        or re.search(r"\bnamba \d+\b", value, re.IGNORECASE)
        or re.search(r"\bnafasi ya \d+\b", value, re.IGNORECASE)
    )


def spoken_text(text: str) -> str:
    value = text.strip()
    pure_number = re.fullmatch(r"(\d+)\.?", value)
    if pure_number:
        return cardinal(int(pure_number.group(1)))

    value = re.sub(
        r"\bZoezi la (\d+)\b",
        lambda match: f"Zoezi la {ORDINALS[int(match.group(1))]}",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\bnafasi ya (\d+)\b",
        lambda match: f"nafasi ya {ORDINALS[int(match.group(1))]}",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\b(\d+)\b",
        lambda match: cardinal(int(match.group(1))),
        value,
    )
    return value


async def synthesize(text: str, destination: Path, semaphore: asyncio.Semaphore) -> None:
    async with semaphore:
        await edge_tts.Communicate(text, VOICE).save(str(destination))


async def main() -> None:
    texts = json.loads((I18N / "texts.json").read_text(encoding="utf-8"))
    audios = json.loads((I18N / "audios.json").read_text(encoding="utf-8"))
    targets = {
        text_id: spoken_text(text)
        for text_id, text in texts.items()
        if isinstance(text, str) and is_target(text) and text_id in audios
    }

    unique_spoken = sorted(set(targets.values()))
    with tempfile.TemporaryDirectory(prefix="kusoma-number-audio-") as temp_dir:
        temp = Path(temp_dir)
        generated = {text: temp / f"audio-{index:03d}.mp3" for index, text in enumerate(unique_spoken)}
        semaphore = asyncio.Semaphore(6)
        await asyncio.gather(
            *(synthesize(text, path, semaphore) for text, path in generated.items())
        )

        audio_dir = I18N / "audio"
        for text_id, speech in targets.items():
            shutil.copyfile(generated[speech], audio_dir / audios[text_id])

    print(f"Updated {len(targets)} audio files using {len(unique_spoken)} Swahili readings.")


if __name__ == "__main__":
    asyncio.run(main())
