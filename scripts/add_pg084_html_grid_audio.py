#!/usr/bin/env python3
"""Build page 84 column narration from verified Rehema letter sounds.

The table audio intentionally contains only the phonics sounds, separated by
fixed pauses.  It does not say ``herufi`` before each sound.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "content" / "i18n" / "sw-TZ"
PAUSE_SECONDS = 0.45
OUTPUT_SUFFIX = "column_sounds_v18"

COLUMNS = {
    "pg084_n0066": {
        "text": "Safu ya kwanza. Herufi a, l, n, u, r, j, s.",
        "sounds": ("a", "la", "na", "u", "ra", "ja", "sa"),
    },
    "pg084_n0067": {
        "text": "Safu ya pili. Herufi m, b, y, c, s, z, h.",
        "sounds": ("ma", "ba", "ya", "cha", "sa", "za", "ha"),
    },
    "pg084_n0068": {
        "text": "Safu ya tatu. Herufi i, k, a, h, m, n, u.",
        "sounds": ("i", "ka", "a", "ha", "ma", "na", "u"),
    },
    "pg084_n0069": {
        "text": "Safu ya nne. Herufi a, z, m, o, j, t, l.",
        "sounds": ("a", "za", "ma", "o", "ja", "ta", "la"),
    },
    "pg084_n0070": {
        "text": "Safu ya tano. Herufi k, w, a, o, w, p, e.",
        "sounds": ("ka", "wa", "a", "o", "wa", "pa", "e"),
    },
}

# These are the standalone sound-by-sound recordings generated with
# sw-TZ-RehemaNeural for bundle version 14.  Reusing them keeps the table
# pronunciation identical to the rest of the book and needs no new TTS call.
SOUND_SOURCES = {
    "a": "pg011_n0012_sound_by_sound_v14.mp3",
    "ba": "pg020_n0007_sound_by_sound_v14.mp3",
    "cha": "pg065_n0020_sound_by_sound_v14.mp3",
    "e": "pg011_n0013_sound_by_sound_v14.mp3",
    "ha": "pg022_n0009_sound_by_sound_v14.mp3",
    "i": "pg011_n0014_sound_by_sound_v14.mp3",
    "ja": "pg046_n0013_sound_by_sound_v14.mp3",
    "ka": "pg022_n0008_sound_by_sound_v14.mp3",
    "la": "pg031_n0011_sound_by_sound_v14.mp3",
    "ma": "pg020_n0009_sound_by_sound_v14.mp3",
    "na": "pg026_n0015_sound_by_sound_v14.mp3",
    "o": "pg011_n0015_sound_by_sound_v14.mp3",
    "pa": "pg024_n0015_sound_by_sound_v14.mp3",
    "ra": "pg056_n0005_sound_by_sound_v14.mp3",
    "sa": "pg028_sec001_ans_item-11_sound_by_sound_v14.mp3",
    "u": "pg011_n0016_sound_by_sound_v14.mp3",
    "wa": "pg059_n0014_sound_by_sound_v14.mp3",
    "ya": "pg046_n0005_sound_by_sound_v14.mp3",
}

# No standalone ``t`` or ``z`` cells occur elsewhere in the book.  Their
# existing v14 recordings contain a prose prefix, a deliberate pause, and the
# required final sound.  The last sound is extracted after that pause.
TAIL_SOUND_SOURCES = {
    "ta": "pg032_n0079_sound_by_sound_v14.mp3",
    "za": "pg048_n0002_sound_by_sound_v14.mp3",
}


def run_ffmpeg(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


def last_pause_end(source: Path) -> float:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-i", str(source),
            "-af", "silencedetect=noise=-45dB:d=0.25", "-f", "null", "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    pause_ends = [
        float(value)
        for value in re.findall(r"silence_end:\s*([0-9.]+)", result.stderr)
    ]
    if not pause_ends:
        raise RuntimeError(f"Could not find the teaching pause in {source.name}")
    return pause_ends[-1]


def to_trimmed_wav(source: Path, destination: Path, start: float = 0.0) -> None:
    arguments: list[str] = []
    if start:
        arguments.extend(["-ss", f"{start:.6f}"])
    arguments.extend(["-i", str(source)])
    arguments.extend([
        "-af",
        (
            "silenceremove="
            "start_periods=1:start_duration=0.03:start_threshold=-50dB:"
            "stop_periods=1:stop_duration=0.08:stop_threshold=-50dB"
        ),
        "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(destination),
    ])
    run_ffmpeg(*arguments)


def assemble(parts: list[Path], silence: Path, destination: Path) -> None:
    concat_file = destination.with_suffix(".txt")
    sequence: list[Path] = []
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


def probe_duration(path: Path) -> float:
    return float(subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1", str(path),
        ],
        text=True,
    ).strip())


def main() -> None:
    texts_path = I18N / "texts.json"
    audios_path = I18N / "audios.json"
    texts = json.loads(texts_path.read_text(encoding="utf-8"))
    audios = json.loads(audios_path.read_text(encoding="utf-8"))

    audio_dir = I18N / "audio"
    required_sounds = {
        sound for values in COLUMNS.values() for sound in values["sounds"]
    }
    missing_sources = sorted(
        sound for sound in required_sounds
        if sound not in SOUND_SOURCES and sound not in TAIL_SOUND_SOURCES
    )
    if missing_sources:
        raise RuntimeError(f"Missing sound sources: {', '.join(missing_sources)}")

    with tempfile.TemporaryDirectory(prefix="kusoma-pg084-columns-") as name:
        temp = Path(name)
        sound_wavs: dict[str, Path] = {}
        for sound in sorted(required_sounds):
            source_name = SOUND_SOURCES.get(sound) or TAIL_SOUND_SOURCES[sound]
            source = audio_dir / source_name
            if not source.is_file():
                raise RuntimeError(f"Missing source recording: {source}")
            output = temp / f"sound_{sound}.wav"
            start = last_pause_end(source) if sound in TAIL_SOUND_SOURCES else 0.0
            to_trimmed_wav(source, output, start)
            sound_wavs[sound] = output

        silence = temp / "pause.wav"
        run_ffmpeg(
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-t", str(PAUSE_SECONDS), "-c:a", "pcm_s16le", str(silence),
        )

        generated: dict[str, str] = {}
        for text_id, values in COLUMNS.items():
            filename = f"{text_id}_{OUTPUT_SUFFIX}.mp3"
            staged = temp / filename
            assemble([sound_wavs[sound] for sound in values["sounds"]], silence, staged)
            duration = probe_duration(staged)
            if staged.stat().st_size <= 0 or not 4.0 <= duration <= 8.0:
                raise RuntimeError(
                    f"Unexpected output for {text_id}: {duration:.3f} seconds"
                )
            shutil.copyfile(staged, audio_dir / filename)
            generated[text_id] = filename

    for text_id, values in COLUMNS.items():
        filename = generated[text_id]
        texts[text_id] = values["text"]
        texts[f"{text_id}_easy_read"] = values["text"]
        audios[text_id] = filename
        audios[f"{text_id}_easy_read"] = filename

    texts_path.write_text(
        json.dumps(texts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    audios_path.write_text(
        json.dumps(audios, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Generated {len(generated)} page 84 sound-only column recordings; "
        f"pauses are {PAUSE_SECONDS:.2f} seconds."
    )


if __name__ == "__main__":
    main()
