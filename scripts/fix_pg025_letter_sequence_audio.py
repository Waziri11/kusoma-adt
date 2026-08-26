#!/usr/bin/env python3
"""Regenerate page 25 letter sequences with explicit, fixed pauses."""

import asyncio
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import edge_tts


ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "content" / "i18n" / "sw-TZ"
VOICE = "sw-TZ-RehemaNeural"
PAUSE_SECONDS = 0.45
TARGETS = {
    "pg025_n0002": (
        "Sauti za herufi zinazounda neno deki ni.",
        ("da", "e", "ka", "i"),
    ),
    "pg025_n0003": (
        "Sauti za herufi zinazounda neno daka ni.",
        ("da", "a", "ka", "a"),
    ),
    "pg025_n0002_easy_read": (
        "Sauti za herufi za neno deki ni.",
        ("da", "e", "ka", "i"),
    ),
    "pg025_n0003_easy_read": (
        "Sauti za herufi za neno daka ni.",
        ("da", "a", "ka", "a"),
    ),
}


async def synthesize(text: str, destination: Path) -> None:
    last_error = None
    for attempt in range(1, 7):
        try:
            await asyncio.wait_for(
                edge_tts.Communicate(text, VOICE, rate="-8%").save(str(destination)),
                timeout=30,
            )
            if destination.stat().st_size <= 0:
                raise RuntimeError("generated file is empty")
            return
        except Exception as error:
            last_error = error
            destination.unlink(missing_ok=True)
            if attempt < 6:
                await asyncio.sleep(attempt * 1.5)
    raise RuntimeError(f"Could not synthesize {text!r}: {last_error}")


def run_ffmpeg(*arguments: str) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *arguments],
        check=True,
    )


def to_wav(source: Path, destination: Path) -> None:
    run_ffmpeg(
        "-i", str(source),
        "-af", (
            "silenceremove="
            "start_periods=1:start_duration=0.05:start_threshold=-50dB:"
            "stop_periods=1:stop_duration=0.12:stop_threshold=-50dB"
        ),
        "-ar", "44100", "-ac", "1",
        "-c:a", "pcm_s16le", str(destination),
    )


def assemble(parts: list[Path], silence: Path, destination: Path) -> None:
    concat_file = destination.with_suffix(".txt")
    sequence = []
    for index, part in enumerate(parts):
        sequence.append(part)
        if index < len(parts) - 1:
            sequence.append(silence)
    concat_file.write_text(
        "".join(f"file '{path}'\n" for path in sequence),
        encoding="utf-8",
    )
    run_ffmpeg(
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c:a", "libmp3lame", "-b:a", "128k", str(destination),
    )


async def main() -> None:
    audios = json.loads((I18N / "audios.json").read_text(encoding="utf-8"))
    missing = sorted(set(TARGETS) - set(audios))
    if missing:
        raise RuntimeError(f"Missing audio mappings: {', '.join(missing)}")

    with tempfile.TemporaryDirectory(prefix="kusoma-pg025-letters-") as temp_name:
        temp = Path(temp_name)
        phrases = {
            *(prefix for prefix, _ in TARGETS.values()),
            *(f"{sound}." for _, sounds in TARGETS.values() for sound in sounds),
        }
        raw_files = {
            phrase: temp / f"raw_{index:02d}.mp3"
            for index, phrase in enumerate(sorted(phrases))
        }
        await asyncio.gather(
            *(synthesize(phrase, path) for phrase, path in raw_files.items())
        )

        wav_files = {}
        for phrase, raw_file in raw_files.items():
            wav_file = raw_file.with_suffix(".wav")
            to_wav(raw_file, wav_file)
            wav_files[phrase] = wav_file

        silence = temp / "pause.wav"
        run_ffmpeg(
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-t", str(PAUSE_SECONDS), "-c:a", "pcm_s16le", str(silence),
        )

        generated = {}
        for text_id, (prefix, sounds) in TARGETS.items():
            output = temp / f"{text_id}.mp3"
            parts = [wav_files[prefix], *(wav_files[f"{sound}."] for sound in sounds)]
            assemble(parts, silence, output)
            generated[text_id] = output

        audio_dir = I18N / "audio"
        for text_id, generated_file in generated.items():
            shutil.copyfile(generated_file, audio_dir / audios[text_id])

    print(
        f"Updated {len(TARGETS)} page-25 recordings with {VOICE}; "
        f"letter pauses are {PAUSE_SECONDS:.2f} seconds."
    )


if __name__ == "__main__":
    asyncio.run(main())
