#!/usr/bin/env python3
"""Build page 86 blank narration from verified Rehema sound clips."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "content" / "i18n" / "sw-TZ"
AUDIO_DIR = I18N / "audio"
PAUSE_SECONDS = 0.45
OUTPUT_SUFFIX = "with_dashes_v19"

TARGETS = {
    "pg086_n0020": ("tha", "dashi", "dashi"),
    "pg086_n0021": ("ng'a", "dashi", "dashi", "dashi"),
}

SOUND_SOURCES = {
    "tha": "pg086_n0020_sound_by_sound_v14.mp3",
    "ng'a": "pg086_n0021_sound_by_sound_v14.mp3",
}

DASH_SOURCE = "pg028_n0022_sound_by_sound_v14.mp3"


def run_ffmpeg(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


def first_pause_start(source: Path) -> float:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-i", str(source),
            "-af", "silencedetect=noise=-45dB:d=0.25", "-f", "null", "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    starts = [
        float(value)
        for value in re.findall(r"silence_start:\s*([0-9.]+)", result.stderr)
    ]
    if not starts:
        raise RuntimeError(f"Could not locate the first pause in {source.name}")
    return starts[0]


def to_trimmed_wav(
    source: Path,
    destination: Path,
    end: float | None = None,
) -> None:
    filters = []
    if end is not None:
        filters.append(f"atrim=end={end:.6f}")
    filters.append(
        "silenceremove="
        "start_periods=1:start_duration=0.03:start_threshold=-50dB:"
        "stop_periods=1:stop_duration=0.08:stop_threshold=-50dB"
    )
    run_ffmpeg(
        "-i", str(source), "-af", ",".join(filters),
        "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(destination),
    )


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
    audios_path = I18N / "audios.json"
    audios = json.loads(audios_path.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory(prefix="kusoma-pg086-dashes-") as name:
        temp = Path(name)
        wavs: dict[str, Path] = {}

        for sound, filename in SOUND_SOURCES.items():
            source = AUDIO_DIR / filename
            if not source.is_file():
                raise RuntimeError(f"Missing source recording: {source}")
            safe_sound = re.sub(r"[^a-z0-9]+", "", sound)
            wav = temp / f"{safe_sound}.wav"
            to_trimmed_wav(source, wav)
            wavs[sound] = wav

        dash_source = AUDIO_DIR / DASH_SOURCE
        dash_wav = temp / "dashi.wav"
        to_trimmed_wav(
            dash_source,
            dash_wav,
            end=first_pause_start(dash_source),
        )
        wavs["dashi"] = dash_wav

        silence = temp / "pause.wav"
        run_ffmpeg(
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-t", str(PAUSE_SECONDS), "-c:a", "pcm_s16le", str(silence),
        )

        for text_id, sequence in TARGETS.items():
            filename = f"{text_id}_{OUTPUT_SUFFIX}.mp3"
            staged = temp / filename
            assemble([wavs[part] for part in sequence], silence, staged)
            duration = probe_duration(staged)
            if staged.stat().st_size <= 0 or not 2.0 <= duration <= 5.0:
                raise RuntimeError(
                    f"Unexpected output for {text_id}: {duration:.3f} seconds"
                )
            shutil.copyfile(staged, AUDIO_DIR / filename)
            audios[text_id] = filename
            audios[f"{text_id}_easy_read"] = filename

    audios_path.write_text(
        json.dumps(audios, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Generated {len(TARGETS)} page 86 recordings with narrated dashes; "
        f"pauses are {PAUSE_SECONDS:.2f} seconds."
    )


if __name__ == "__main__":
    main()
