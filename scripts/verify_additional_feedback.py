#!/usr/bin/env python3
"""Verify the v28 additional-feedback text, semantics, audio, and cache state."""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LANG = ROOT / "content" / "i18n" / "sw-TZ"
MATRIX = ROOT / "reports" / "additional-feedback-correction-matrix-v28.json"
VERSION = "28"


class IdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("data-id"):
            self.ids.append(str(values["data-id"]))


def probe_and_measure(path: Path) -> tuple[float, float]:
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_name", "-show_entries", "format=duration",
            "-of", "json", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(probe.stdout)
    streams = data.get("streams", [])
    duration = float(data.get("format", {}).get("duration", 0))
    if not streams or streams[0].get("codec_name") != "mp3" or duration <= 0:
        raise RuntimeError(f"Invalid MP3 stream: {path.name}")
    volume = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect",
            "-f", "null", "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    match = re.search(r"max_volume:\s*(-?[0-9.]+) dB", volume.stderr)
    if not match:
        raise RuntimeError(f"No measurable audio signal: {path.name}")
    maximum = float(match.group(1))
    if maximum < -45:
        raise RuntimeError(f"Effectively silent audio: {path.name} ({maximum} dB)")
    return duration, maximum


def silence_count(path: Path) -> int:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-i", str(path), "-af",
            "silencedetect=noise=-45dB:d=0.35", "-f", "null", "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return len(re.findall(r"silence_end:", result.stderr))


def main() -> None:
    texts: dict[str, str] = json.loads((LANG / "texts.json").read_text(encoding="utf-8"))
    audios: dict[str, str] = json.loads((LANG / "audios.json").read_text(encoding="utf-8"))
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    rows = matrix["corrections"]
    if matrix.get("stable_base_id_count") != 166 or matrix.get("text_entry_count") != 332:
        raise RuntimeError("Unexpected correction-matrix counts")

    target_ids: list[str] = []
    for row in rows:
        entries = [(row["base_id"], row["normal"])]
        if "easy_read" in row:
            entries.append((row["easy_read"]["text_id"], row["easy_read"]))
        for text_id, entry in entries:
            if texts.get(text_id) != entry["expected_new"]:
                raise RuntimeError(f"{text_id}: current text differs from expected_new")
            expected_audio = f"{text_id}_feedback_v28.mp3"
            if audios.get(text_id) != expected_audio:
                raise RuntimeError(f"{text_id}: stale or missing v28 audio mapping")
            target_ids.append(text_id)

    if any("bainsiha" in value.lower() for value in texts.values() if isinstance(value, str)):
        raise RuntimeError("texts.json still contains 'bainsiha'")

    html_files = sorted(ROOT.glob("*.html"))
    if len(html_files) != 104:
        raise RuntimeError(f"Expected 104 root HTML files, found {len(html_files)}")
    for page in html_files:
        source = page.read_text(encoding="utf-8")
        if "?v=27" in source:
            raise RuntimeError(f"{page.name}: stale v27 query")
        for required in (
            f"./assets/offline-preloader.js?v={VERSION}",
            f"./assets/image-description-default.js?v={VERSION}",
            f"./assets/base.bundle.local.js?v={VERSION}",
        ):
            if required not in source:
                raise RuntimeError(f"{page.name}: missing {required}")
        parsed = IdParser()
        parsed.feed(source)
        duplicates = [text_id for text_id, count in Counter(parsed.ids).items() if count > 1]
        if duplicates:
            raise RuntimeError(f"{page.name}: duplicate data-id values: {duplicates}")

    config = json.loads((ROOT / "assets" / "config.json").read_text(encoding="utf-8"))
    if str(config.get("bundleVersion")) != VERSION:
        raise RuntimeError("assets/config.json is not bundleVersion 28")
    preloader = (ROOT / "assets" / "offline-preloader.js").read_text(encoding="utf-8")
    if preloader.count("feedback_v28") != 332 or '"bundleVersion":"28"' not in preloader:
        raise RuntimeError("Offline preloader is missing v28 text/audio state")

    pg97 = (ROOT / "pg097_sec001.html").read_text(encoding="utf-8")
    for image_id in ("pg097_im003", "pg097_im004"):
        if f'data-id="{image_id}"' in pg97:
            raise RuntimeError(f"Page 97 still narrates presentation image {image_id}")
    if pg97.count('aria-hidden="true"') < 2:
        raise RuntimeError("Page 97 presentation images are not both hidden semantically")

    pg98 = (ROOT / "pg098_sec001.html").read_text(encoding="utf-8")
    order = [pg98.index(f'data-id="{text_id}"') for text_id in (
        "pg098_n0010", "pg098_n0011", "pg098_im004"
    )]
    if order != sorted(order):
        raise RuntimeError("Page 98 narration nodes are not in heading/instruction/chart order")

    for page_name in ("pg085_sec001.html", "pg086_sec001.html"):
        source = (ROOT / page_name).read_text(encoding="utf-8")
        if f"./assets/kusoma-emphasis.js?v={VERSION}" not in source:
            raise RuntimeError(f"{page_name}: missing persistent emphasis helper")
    if (ROOT / "pg085_sec001.html").read_text(encoding="utf-8").count("<strong") != 1:
        raise RuntimeError("Page 85 fallback emphasis count is not 1")
    if (ROOT / "pg086_sec001.html").read_text(encoding="utf-8").count("<strong") != 5:
        raise RuntimeError("Page 86 fallback emphasis count is not 5")

    audio_paths = [LANG / "audio" / audios[text_id] for text_id in target_ids]
    missing = [path.name for path in audio_paths if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise RuntimeError(f"Missing or empty generated audio: {missing[:10]}")
    with ThreadPoolExecutor(max_workers=8) as executor:
        measurements = list(executor.map(probe_and_measure, audio_paths))

    from add_pg084_html_grid_audio import COLUMNS
    pg84_count = 0
    for text_id, values in COLUMNS.items():
        pg84_count += len(values["sounds"])
        filename = audios.get(text_id)
        if filename != f"{text_id}_column_sounds_v18.mp3":
            raise RuntimeError(f"{text_id}: page 84 sound-only mapping drift")
        path = LANG / "audio" / filename
        probe_and_measure(path)
        if silence_count(path) < len(values["sounds"]) - 1:
            raise RuntimeError(f"{text_id}: insufficient natural pauses")
    if pg84_count != 35:
        raise RuntimeError(f"Page 84 expected 35 chart letters, found {pg84_count}")

    durations = [duration for duration, _ in measurements]
    maxima = [maximum for _, maximum in measurements]
    print(
        "PASS: 166 stable IDs / 332 normal+Easy Read entries; 332 fresh MP3s "
        "ffprobe-validated and non-silent; 104 v28 HTML files; page 84 has 35 "
        "ordered sound tokens; page 97/98 semantics and persistent emphasis verified. "
        f"New-audio duration range {min(durations):.3f}-{max(durations):.3f}s, "
        f"max-volume range {min(maxima):.1f}-{max(maxima):.1f} dB."
    )


if __name__ == "__main__":
    main()
