#!/usr/bin/env python3
"""Regenerate all explicit letter/sound narration with fixed teaching pauses.

Visible text remains unchanged. This script finds mapped narration that either:

1. contains the word ``herufi`` and one or more isolated graphemes; or
2. consists only of a grapheme used as a standalone exercise item.

Each grapheme is synthesized as its Kiswahili sound (for example ``d`` becomes
``da`` and ``k`` becomes ``ka``), then the sentence is reassembled with a
fixed pause before the narration continues.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import edge_tts


ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "content" / "i18n" / "sw-TZ"
VOICE = "sw-TZ-RehemaNeural"
OUTPUT_SUFFIX = "sound_by_sound_v14"
PAUSE_SECONDS = 0.45

# The readings follow the phonics style requested for this book: consonants
# are pronounced as short open syllables rather than English letter names.
READINGS: Dict[str, Tuple[str, ...]] = {
    "a": ("a",),
    "b": ("ba",),
    "c": ("cha",),
    "d": ("da",),
    "e": ("e",),
    "f": ("fa",),
    "g": ("ga",),
    "h": ("ha",),
    "i": ("i",),
    "j": ("ja",),
    "k": ("ka",),
    "l": ("la",),
    "m": ("ma",),
    "n": ("na",),
    "o": ("o",),
    "p": ("pa",),
    "q": ("kwa",),
    "r": ("ra",),
    "s": ("sa",),
    "t": ("ta",),
    "u": ("u",),
    "v": ("va",),
    "w": ("wa",),
    "x": ("ksa",),
    "y": ("ya",),
    "z": ("za",),
    "ch": ("cha",),
    "sh": ("sha",),
    "th": ("tha",),
    "dh": ("dha",),
    "mb": ("mba",),
    "ny": ("nya",),
    "ng": ("nga",),
    "nd": ("nda",),
    "kw": ("kwa",),
    "ng'": ("ng'a",),
    "ng’": ("ng'a",),
    "mbw": ("mbwa",),
    "ngw": ("ngwa",),
    "chw": ("chwa",),
    "nyw": ("nywa",),
    "ndw": ("ndwa",),
    # The page-66 image intentionally contains reversed ``hc`` distractors.
    # Read those as the two displayed letters instead of inventing a digraph.
    "hc": ("ha", "cha"),
}

TOKEN_KEYS = sorted(READINGS, key=len, reverse=True)
TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z])(?:"
    + "|".join(re.escape(token) for token in TOKEN_KEYS)
    + r")(?![A-Za-z])",
    re.IGNORECASE,
)
SPACED_TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z])(?:"
    + "|".join(re.escape(token) for token in TOKEN_KEYS)
    + r")(?![A-Za-z])\s+(?<![A-Za-z])(?:"
    + "|".join(re.escape(token) for token in TOKEN_KEYS)
    + r")(?![A-Za-z])",
    re.IGNORECASE,
)
TEACHING_CONTEXT_PATTERN = re.compile(
    r"\b(?:herufi|sauti|tamka|unganisha|silabi|konsonanti|irabu|vokali)\b",
    re.IGNORECASE,
)

# This is a Roman-numeral page marker in the front matter, not a phonics item.
EXCLUDED_STANDALONE_IDS = {"pg005_n0022"}

Segment = Tuple[str, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Report target counts without synthesizing or changing files.",
    )
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--retries", type=int, default=6)
    return parser.parse_args()


def clean_prose(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip(" \t\r\n-–—•,;:")
    if not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]", cleaned):
        return ""
    return cleaned


def normalize_synthesis_text(value: str) -> str:
    value = value.strip()
    if value and value[-1] not in ".!?":
        value += "."
    return value


def detected_tokens(value: str) -> List[str]:
    return [match.group(0) for match in TOKEN_PATTERN.finditer(value)]


def segments_for(value: str) -> List[Segment]:
    segments: List[Segment] = []
    position = 0
    for match in TOKEN_PATTERN.finditer(value):
        prose = clean_prose(value[position : match.start()])
        if prose:
            segments.append(("prose", prose))
        token = match.group(0).lower()
        segments.extend(("sound", reading) for reading in READINGS[token])
        position = match.end()
    prose = clean_prose(value[position:])
    if prose:
        segments.append(("prose", prose))
    return segments


def is_target(text_id: str, value: str) -> bool:
    stripped = value.strip()
    tokens = detected_tokens(value)
    in_explicit_letter_context = (
        bool(tokens) and TEACHING_CONTEXT_PATTERN.search(value) is not None
    )
    is_fill_in_letter_row = (
        bool(tokens)
        and ("dashi" in value.lower() or "_" in value)
    )
    is_advanced_formation_row = (
        text_id.startswith(("pg086_", "pg091_"))
        and SPACED_TOKEN_PATTERN.search(value) is not None
    )
    is_letter_glossary_example = text_id.startswith("gl") and len(tokens) >= 2
    is_known_unlabelled_letter_list = text_id == "pg003_n0029"
    is_standalone_grapheme = (
        text_id not in EXCLUDED_STANDALONE_IDS
        and stripped.lower() in READINGS
    )
    return any(
        (
            in_explicit_letter_context,
            is_fill_in_letter_row,
            is_advanced_formation_row,
            is_letter_glossary_example,
            is_known_unlabelled_letter_list,
            is_standalone_grapheme,
        )
    )


def build_targets(
    texts: Dict[str, str], audios: Dict[str, str]
) -> Dict[str, List[Segment]]:
    targets = {
        text_id: segments_for(value)
        for text_id, value in texts.items()
        if text_id in audios
        and isinstance(value, str)
        and is_target(text_id, value)
    }
    empty = sorted(text_id for text_id, segments in targets.items() if not segments)
    if empty:
        raise RuntimeError(f"Targets produced no spoken segments: {', '.join(empty)}")
    return targets


def unit_filename(unit: Segment, suffix: str) -> str:
    digest = hashlib.sha256(f"{unit[0]}\0{unit[1]}".encode("utf-8")).hexdigest()
    return f"unit_{digest[:20]}.{suffix}"


async def synthesize_unit(
    unit: Segment,
    destination: Path,
    semaphore: asyncio.Semaphore,
    retries: int,
) -> None:
    text = normalize_synthesis_text(unit[1])
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            async with semaphore:
                await asyncio.wait_for(
                    edge_tts.Communicate(text, VOICE, rate="-8%").save(
                        str(destination)
                    ),
                    timeout=40,
                )
            if destination.stat().st_size <= 0:
                raise RuntimeError("generated file is empty")
            return
        except Exception as error:
            last_error = error
            destination.unlink(missing_ok=True)
            if attempt < retries:
                await asyncio.sleep(attempt * 1.5)
    raise RuntimeError(f"Could not synthesize {text!r}: {last_error}")


def run_ffmpeg(*arguments: str) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *arguments],
        check=True,
    )


def to_wav(source: Path, destination: Path) -> None:
    run_ffmpeg(
        "-i",
        str(source),
        "-af",
        (
            "silenceremove="
            "start_periods=1:start_duration=0.05:start_threshold=-50dB:"
            "stop_periods=1:stop_duration=0.12:stop_threshold=-50dB"
        ),
        "-ar",
        "44100",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(destination),
    )


def assemble(
    text_id: str,
    segments: Sequence[Segment],
    wav_files: Dict[Segment, Path],
    silence: Path,
    stage: Path,
) -> Path:
    output = stage / f"{text_id}_{OUTPUT_SUFFIX}.mp3"
    concat_file = stage / f"concat_{text_id}.txt"
    sequence: List[Path] = []
    for index, segment in enumerate(segments):
        sequence.append(wav_files[segment])
        if index < len(segments) - 1:
            sequence.append(silence)
    concat_file.write_text(
        "".join(f"file '{path}'\n" for path in sequence),
        encoding="utf-8",
    )
    run_ffmpeg(
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c:a",
        "libmp3lame",
        "-b:a",
        "128k",
        str(output),
    )
    return output


def probe_audio(path: Path) -> Dict[str, object]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,sample_rate,channels",
            "-show_entries",
            "format=duration,size",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    duration = float(data.get("format", {}).get("duration", 0))
    if not streams or streams[0].get("codec_name") != "mp3" or duration <= 0:
        raise RuntimeError(f"Invalid generated MP3: {path}")
    return {
        "duration_seconds": round(duration, 3),
        "size_bytes": int(data["format"]["size"]),
        "codec": streams[0]["codec_name"],
        "sample_rate": int(streams[0]["sample_rate"]),
        "channels": int(streams[0]["channels"]),
    }


def chunks(values: Sequence[Segment], size: int) -> Iterable[Sequence[Segment]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


async def main() -> None:
    args = parse_args()
    texts_path = I18N / "texts.json"
    audios_path = I18N / "audios.json"
    texts = json.loads(texts_path.read_text(encoding="utf-8"))
    audios = json.loads(audios_path.read_text(encoding="utf-8"))
    targets = build_targets(texts, audios)
    normal_count = sum(not text_id.endswith("_easy_read") for text_id in targets)
    easy_count = len(targets) - normal_count
    units = sorted(
        {segment for segments in targets.values() for segment in segments},
        key=lambda item: (item[0], item[1]),
    )

    print(
        f"Audit: {len(targets)} mapped narration targets "
        f"({normal_count} normal, {easy_count} easy-read), "
        f"{len(units)} unique synthesis units."
    )
    if args.audit_only:
        return

    with tempfile.TemporaryDirectory(prefix="kusoma-all-letter-sounds-") as name:
        stage = Path(name)
        raw_files = {
            unit: stage / unit_filename(unit, "mp3")
            for unit in units
        }
        semaphore = asyncio.Semaphore(args.concurrency)
        for batch_number, batch in enumerate(chunks(units, 60), start=1):
            await asyncio.gather(
                *(
                    synthesize_unit(
                        unit,
                        raw_files[unit],
                        semaphore,
                        args.retries,
                    )
                    for unit in batch
                )
            )
            print(f"Synthesized unit batch {batch_number}.", flush=True)

        wav_files: Dict[Segment, Path] = {}
        for index, unit in enumerate(units, start=1):
            wav = stage / unit_filename(unit, "wav")
            to_wav(raw_files[unit], wav)
            wav_files[unit] = wav
            if index % 80 == 0 or index == len(units):
                print(f"Prepared {index}/{len(units)} reusable audio units.", flush=True)

        silence = stage / "pause.wav"
        run_ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            str(PAUSE_SECONDS),
            "-c:a",
            "pcm_s16le",
            str(silence),
        )

        target_items = sorted(targets.items())
        generated: Dict[str, Path] = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                text_id: executor.submit(
                    assemble,
                    text_id,
                    segments,
                    wav_files,
                    silence,
                    stage,
                )
                for text_id, segments in target_items
            }
            for index, (text_id, future) in enumerate(futures.items(), start=1):
                generated[text_id] = future.result()
                if index % 100 == 0 or index == len(futures):
                    print(f"Assembled {index}/{len(futures)} recordings.", flush=True)

        probes: Dict[str, Dict[str, object]] = {}
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                text_id: executor.submit(probe_audio, path)
                for text_id, path in generated.items()
            }
            for index, (text_id, future) in enumerate(futures.items(), start=1):
                probes[text_id] = future.result()
                if index % 150 == 0 or index == len(futures):
                    print(f"Verified {index}/{len(futures)} recordings with ffprobe.", flush=True)

        audio_dir = I18N / "audio"
        updated_audios = dict(audios)
        for text_id, generated_file in generated.items():
            filename = generated_file.name
            shutil.copyfile(generated_file, audio_dir / filename)
            updated_audios[text_id] = filename

        staged_json = audios_path.with_suffix(".json.tmp")
        staged_json.write_text(
            json.dumps(updated_audios, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        staged_json.replace(audios_path)

        report_dir = ROOT / "reports"
        report_dir.mkdir(exist_ok=True)
        report_path = report_dir / "letter-sound-audio-audit-v14.json"
        report = {
            "voice": VOICE,
            "pause_seconds": PAUSE_SECONDS,
            "selection_rule": (
                "Mapped text with explicit graphemes in a phonics teaching "
                "context, fill-in rows, advanced formation rows, letter glossary "
                "examples, and standalone grapheme exercise items; excludes the "
                "pg005_n0022 Roman-numeral page marker."
            ),
            "target_count": len(targets),
            "normal_count": normal_count,
            "easy_read_count": easy_count,
            "unique_synthesis_units": len(units),
            "targets": [
                {
                    "text_id": text_id,
                    "display_text": texts[text_id],
                    "detected_graphemes": detected_tokens(texts[text_id]),
                    "spoken_segments": [value for _, value in targets[text_id]],
                    "audio_filename": updated_audios[text_id],
                    **probes[text_id],
                }
                for text_id in sorted(targets)
            ],
        }
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(
        f"Updated {len(targets)} mappings and recordings with {VOICE}; "
        f"fixed pauses are {PAUSE_SECONDS:.2f} seconds."
    )


if __name__ == "__main__":
    asyncio.run(main())
