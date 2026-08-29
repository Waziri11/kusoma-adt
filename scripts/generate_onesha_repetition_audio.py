#!/usr/bin/env python3
"""Generate cache-safe RehemaNeural audio for the bundle v43 corrections."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import edge_tts

from apply_onesha_repetition_v43 import TARGET_BASE_IDS


ROOT = Path(__file__).resolve().parents[1]
LANG = ROOT / "content" / "i18n" / "sw-TZ"
VOICE = "sw-TZ-RehemaNeural"
SUFFIX = "onesha_v43"
SPLIT_NARRATION = "Onesha herufi g.\nKisha tamka sauti yake."


def spoken_text(value: str) -> str:
    return value.replace(" / ", " au ").strip()


def assert_audible(path: Path) -> None:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect",
            "-f", "null", "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    match = re.search(r"max_volume:\s*(-?[0-9.]+) dB", result.stderr)
    if not match or float(match.group(1)) < -45:
        raise RuntimeError("generated an effectively silent MP3")


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
    items: list[tuple[str, str]] = []
    for text_id in target_ids:
        visible = texts.get(text_id)
        if not isinstance(visible, str) or not visible.strip():
            raise RuntimeError(f"{text_id}: missing corrected visible text")
        if "herufi ya herufi" in visible or "herufi za herufi" in visible:
            raise RuntimeError(f"{text_id}: repeated-herufi text remains")
        if "Onesha" in visible and "/ bainisha" in visible:
            raise RuntimeError(f"{text_id}: Onesha still contains / bainisha")
        items.append((text_id, spoken_text(visible)))

    unique_spoken = sorted({spoken for _, spoken in items})
    semaphore = asyncio.Semaphore(args.concurrency)
    with tempfile.TemporaryDirectory(prefix="kusoma-onesha-v43-") as temp_name:
        temp = Path(temp_name)
        generated = {
            spoken: temp / f"spoken-{index:03d}.mp3"
            for index, spoken in enumerate(unique_spoken)
        }

        async def synthesize_single(spoken: str, destination: Path) -> None:
            last_error: Exception | None = None
            for attempt in range(1, args.retries + 1):
                try:
                    async with semaphore:
                        await asyncio.wait_for(
                            edge_tts.Communicate(spoken, VOICE).save(str(destination)),
                            timeout=45,
                        )
                    if not destination.is_file() or destination.stat().st_size == 0:
                        raise RuntimeError("generated an empty MP3")
                    assert_audible(destination)
                    return
                except Exception as error:
                    last_error = error
                    destination.unlink(missing_ok=True)
                    if attempt < args.retries:
                        await asyncio.sleep(min(2 ** (attempt - 1), 20))
            raise RuntimeError(f"TTS failed after {args.retries} attempts: {spoken!r}") from last_error

        async def synthesize(spoken: str, destination: Path) -> None:
            if spoken != SPLIT_NARRATION:
                await synthesize_single(spoken, destination)
                return

            first = destination.with_name(f"{destination.stem}-first.mp3")
            second = destination.with_name(f"{destination.stem}-second.mp3")
            await asyncio.gather(
                synthesize_single("Onesha herufi g.", first),
                synthesize_single("Kisha tamka sauti yake.", second),
            )
            subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(first),
                    "-f", "lavfi", "-t", "0.35", "-i", "anullsrc=r=24000:cl=mono",
                    "-i", str(second),
                    "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[a]",
                    "-map", "[a]", "-codec:a", "libmp3lame", "-q:a", "3",
                    str(destination),
                ],
                check=True,
            )
            assert_audible(destination)

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
        f"{len(unique_spoken)} unique spoken sentences; remaining slashes narrated as 'au'."
    )


if __name__ == "__main__":
    asyncio.run(main())
