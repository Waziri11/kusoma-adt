#!/usr/bin/env python3
"""Verify bundle v43 Onesha/repetition text, audio, and offline consistency."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import json
import re
import subprocess
from pathlib import Path

from apply_onesha_repetition_v43 import MATRIX_PATH, ROOT, TARGET_BASE_IDS, VERSION


LANG = ROOT / "content" / "i18n" / "sw-TZ"
REPEATED = re.compile(r"\bherufi\s+(?:ya|za)\s+herufi\b", re.IGNORECASE)


class DataIdTextParser(HTMLParser):
    def __init__(self, target_id: str) -> None:
        super().__init__(convert_charrefs=True)
        self.target_id = target_id
        self.depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.depth:
            self.depth += 1
        elif dict(attrs).get("data-id") == self.target_id:
            self.depth = 1

    def handle_endtag(self, tag: str) -> None:
        if self.depth:
            self.depth -= 1

    def handle_data(self, data: str) -> None:
        if self.depth:
            self.parts.append(data)


def html_text(page: Path, text_id: str) -> str:
    parser = DataIdTextParser(text_id)
    parser.feed(page.read_text(encoding="utf-8"))
    return re.sub(r"\s+", " ", "".join(parser.parts)).strip()


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
    duration = float(data.get("format", {}).get("duration", 0))
    streams = data.get("streams", [])
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
        raise RuntimeError(f"No measurable signal: {path.name}")
    maximum = float(match.group(1))
    if maximum < -45:
        raise RuntimeError(f"Effectively silent audio: {path.name} ({maximum} dB)")
    return duration, maximum


def main() -> None:
    texts = json.loads((LANG / "texts.json").read_text(encoding="utf-8"))
    audios = json.loads((LANG / "audios.json").read_text(encoding="utf-8"))
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    if matrix.get("stable_base_id_count") != 29 or matrix.get("text_entry_count") != 58:
        raise RuntimeError("Unexpected correction matrix counts")
    rows = matrix["corrections"]
    if {row["base_id"] for row in rows} != TARGET_BASE_IDS:
        raise RuntimeError("Correction matrix target set drift")

    target_ids: list[str] = []
    for row in rows:
        base_id = row["base_id"]
        page = ROOT / f"{base_id.split('_', 1)[0]}_sec001.html"
        expected_normal = row["normal"]["expected_new"]
        if texts.get(base_id) != expected_normal:
            raise RuntimeError(f"{base_id}: normal text mismatch")
        if html_text(page, base_id) != re.sub(r"\s+", " ", expected_normal).strip():
            raise RuntimeError(f"{base_id}: HTML/texts.json mismatch")
        for entry_name in ("normal", "easy_read"):
            entry = row[entry_name]
            text_id = entry["text_id"]
            if texts.get(text_id) != entry["expected_new"]:
                raise RuntimeError(f"{text_id}: expected_new mismatch")
            expected_audio = f"{text_id}_onesha_v43.mp3"
            if audios.get(text_id) != expected_audio:
                raise RuntimeError(f"{text_id}: stale audio mapping")
            target_ids.append(text_id)

    for text_id, value in texts.items():
        if not isinstance(value, str):
            continue
        if REPEATED.search(value):
            raise RuntimeError(f"{text_id}: repeated-herufi wording remains: {value!r}")
        if "Onesha" in value and "/ bainisha" in value:
            raise RuntimeError(f"{text_id}: Onesha still contains / bainisha: {value!r}")

    for page in sorted(ROOT.glob("*.html")):
        source = page.read_text(encoding="utf-8")
        if REPEATED.search(source):
            raise RuntimeError(f"{page.name}: repeated-herufi wording remains")
        if re.search(r"Onesha[\s\S]{0,120}/\s*bainisha", source, re.IGNORECASE):
            raise RuntimeError(f"{page.name}: Onesha still contains / bainisha")

    page31 = ROOT / "pg031_sec001.html"
    references = {
        "pg031_n0003": "Tamka / bainisha sauti ya herufi hii.",
        "pg031_n0007": "Onesha na tamka sauti ya herufi l.",
    }
    for text_id, expected in references.items():
        if texts.get(text_id) != expected or html_text(page31, text_id) != expected:
            raise RuntimeError(f"{text_id}: page 31 reference wording mismatch")

    html_files = sorted(ROOT.glob("*.html"))
    if len(html_files) != 104:
        raise RuntimeError(f"Expected 104 root HTML files, found {len(html_files)}")
    required_assets = (
        f"./assets/offline-preloader.js?v={VERSION}",
        f"./assets/image-description-default.js?v={VERSION}",
        f"./assets/base.bundle.local.js?v={VERSION}",
    )
    for page in html_files:
        source = page.read_text(encoding="utf-8")
        for required in required_assets:
            if required not in source:
                raise RuntimeError(f"{page.name}: missing {required}")

    config = json.loads((ROOT / "assets" / "config.json").read_text(encoding="utf-8"))
    if str(config.get("bundleVersion")) != VERSION:
        raise RuntimeError(f"assets/config.json is not bundleVersion {VERSION}")
    preloader = (ROOT / "assets" / "offline-preloader.js").read_text(encoding="utf-8")
    if f'"bundleVersion":"{VERSION}"' not in preloader:
        raise RuntimeError("Offline preloader has stale config")
    if preloader.count("_onesha_v43.mp3") != 58:
        raise RuntimeError("Offline preloader does not contain all 58 new audio mappings")

    audio_paths = [LANG / "audio" / audios[text_id] for text_id in target_ids]
    missing = [path.name for path in audio_paths if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise RuntimeError(f"Missing or empty generated audio: {missing[:10]}")
    with ThreadPoolExecutor(max_workers=8) as executor:
        measurements = list(executor.map(probe_and_measure, audio_paths))
    durations = [duration for duration, _ in measurements]
    maxima = [maximum for _, maximum in measurements]
    print(
        "PASS: 29 normal + 29 Easy Read corrections; 58 RehemaNeural MP3s "
        "decode and contain signal; 104 v43 HTML pages; page 31 reference preserved. "
        f"Duration {min(durations):.3f}-{max(durations):.3f}s; "
        f"max volume {min(maxima):.1f}-{max(maxima):.1f} dB."
    )


if __name__ == "__main__":
    main()
