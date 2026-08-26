#!/usr/bin/env python3
"""Verify installed whole-book letter/sound audio, mappings, and pause structure."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Tuple


ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "content" / "i18n" / "sw-TZ"
REPORT = ROOT / "reports" / "letter-sound-audio-audit-v14.json"
EXPECTED_VERSION = "14"


def load_generator():
    path = ROOT / "scripts" / "fix_all_letter_sound_audio.py"
    spec = importlib.util.spec_from_file_location("letter_sound_generator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def probe(path: Path) -> Dict[str, object]:
    completed = subprocess.run(
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
    data = json.loads(completed.stdout)
    stream = data["streams"][0]
    duration = float(data["format"]["duration"])
    if stream["codec_name"] != "mp3" or duration <= 0:
        raise RuntimeError(f"Invalid audio stream: {path}")
    return {
        "duration": duration,
        "sample_rate": int(stream["sample_rate"]),
        "channels": int(stream["channels"]),
        "size": int(data["format"]["size"]),
    }


def pause_count(path: Path) -> int:
    completed = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(path),
            "-af",
            "silencedetect=noise=-45dB:d=0.30",
            "-f",
            "null",
            "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return len(re.findall(r"silence_duration:", completed.stderr))


def verify_one(row: Dict[str, object], audios: Dict[str, str]) -> Tuple[str, float]:
    text_id = str(row["text_id"])
    filename = str(row["audio_filename"])
    if audios.get(text_id) != filename:
        raise RuntimeError(f"Mapping mismatch for {text_id}")
    path = I18N / "audio" / filename
    if not path.is_file():
        raise RuntimeError(f"Missing installed audio: {path}")
    metadata = probe(path)
    expected_pauses = max(0, len(row["spoken_segments"]) - 1)
    if expected_pauses:
        observed_pauses = pause_count(path)
        if observed_pauses < expected_pauses:
            raise RuntimeError(
                f"{text_id}: expected at least {expected_pauses} pauses, "
                f"found {observed_pauses}"
            )
    return text_id, float(metadata["duration"])


def main() -> None:
    texts = json.loads((I18N / "texts.json").read_text(encoding="utf-8"))
    audios = json.loads((I18N / "audios.json").read_text(encoding="utf-8"))
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    rows = report["targets"]

    generator = load_generator()
    current_targets = set(generator.build_targets(texts, audios))
    report_targets = {row["text_id"] for row in rows}
    if current_targets != report_targets:
        missing = sorted(current_targets - report_targets)
        extra = sorted(report_targets - current_targets)
        raise RuntimeError(
            f"Audit target drift; missing={missing[:10]}, extra={extra[:10]}"
        )
    if len(rows) != 883 or len(report_targets) != 883:
        raise RuntimeError("Expected exactly 883 unique audited targets")

    config = json.loads((ROOT / "assets" / "config.json").read_text())
    if config.get("bundleVersion") != EXPECTED_VERSION:
        raise RuntimeError("Bundle version is not 14")
    html_files = sorted(ROOT.glob("*.html"))
    if len(html_files) != 104:
        raise RuntimeError(f"Expected 104 HTML files, found {len(html_files)}")
    for html in html_files:
        source = html.read_text(encoding="utf-8")
        if (
            f"offline-preloader.js?v={EXPECTED_VERSION}" not in source
            or f"base.bundle.local.js?v={EXPECTED_VERSION}" not in source
        ):
            raise RuntimeError(f"Stale bundle query string in {html.name}")

    preloader = (ROOT / "assets" / "offline-preloader.js").read_text(
        encoding="utf-8"
    )
    if preloader.count("sound_by_sound_v14") != 883:
        raise RuntimeError("Offline preloader does not contain all 883 mappings")

    results = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(verify_one, row, audios) for row in rows]
        for index, future in enumerate(futures, start=1):
            results.append(future.result())
            if index % 150 == 0 or index == len(futures):
                print(f"Verified {index}/{len(futures)} installed recordings.")

    durations = [duration for _, duration in results]
    print(
        "PASS: 883 current targets, mappings, MP3 streams, pause structures, "
        f"offline mappings, and 104 version-14 HTML files verified. "
        f"Duration range: {min(durations):.3f}-{max(durations):.3f}s."
    )


if __name__ == "__main__":
    main()
