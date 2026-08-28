#!/usr/bin/env python3
"""Verify that every manifest image can participate in read-aloud."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
LANG_DIR = ROOT / "content" / "i18n" / "sw-TZ"
MIGRATION_ASSET = "./assets/image-description-default.js"


class ImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images: list[dict[str, str]] = []
        self.scripts: list[str] = []
        self.data_ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if values.get("data-id"):
            self.data_ids.add(values["data-id"])
        if tag.lower() == "img":
            self.images.append(values)
        elif tag.lower() == "script" and values.get("src"):
            self.scripts.append(values["src"])


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def probe_mp3(path: Path) -> str | None:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name,duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return f"{path.name}: ffprobe failed: {result.stderr.strip()}"
    streams = []
    try:
        streams = json.loads(result.stdout).get("streams", [])
        duration = float(streams[0].get("duration", 0)) if streams else 0
    except (IndexError, TypeError, ValueError, json.JSONDecodeError):
        duration = 0
    if not streams or streams[0].get("codec_name") != "mp3" or duration <= 0:
        return f"{path.name}: missing a positive-duration MP3 audio stream"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-ffprobe",
        action="store_true",
        help="Skip codec and duration validation.",
    )
    args = parser.parse_args()

    pages = load_json(ROOT / "content" / "pages.json")
    texts: dict[str, str] = load_json(LANG_DIR / "texts.json")
    audios: dict[str, str] = load_json(LANG_DIR / "audios.json")
    config = load_json(ROOT / "assets" / "config.json")
    bundle_version = str(config.get("bundleVersion", ""))
    errors: list[str] = []
    image_occurrences = 0
    mapped_ids: set[str] = set()
    mp3_paths: set[Path] = set()

    if config.get("features", {}).get("describeImages") is not True:
        errors.append("assets/config.json must enable features.describeImages")
    if not (ROOT / "assets" / "image-description-default.js").is_file():
        errors.append("missing assets/image-description-default.js")

    for page in pages:
        href = page.get("href")
        if not href:
            errors.append(f"manifest entry has no href: {page!r}")
            continue
        html_path = ROOT / href
        if not html_path.is_file():
            errors.append(f"missing manifest page: {href}")
            continue

        html = html_path.read_text(encoding="utf-8")
        parsed = ImageParser()
        parsed.feed(html)

        expected_preloader = f"./assets/offline-preloader.js?v={bundle_version}"
        expected_migration = f"{MIGRATION_ASSET}?v={bundle_version}"
        expected_runtime = f"./assets/base.bundle.local.js?v={bundle_version}"
        expected_scripts = [expected_preloader, expected_migration, expected_runtime]
        try:
            positions = [parsed.scripts.index(src) for src in expected_scripts]
        except ValueError:
            errors.append(f"{href}: missing one of the versioned read-aloud scripts")
        else:
            if positions != sorted(positions):
                errors.append(f"{href}: image narration migration must load before the runtime")

        for image in parsed.images:
            image_occurrences += 1
            image_id = image.get("data-id", "").strip()
            src = image.get("src", "").strip()
            alt = image.get("alt", "").strip()
            if not image_id:
                # Some layouts use one narrated image ID for a composite pair,
                # repeat an already narrated asset inside a hidden activity
                # template, or place the ID on an adjacent sr-only proxy span.
                # Those images must not become duplicate read-aloud units.
                proxy_id = Path(src).stem if src else ""
                if image.get("aria-hidden") == "true":
                    continue
                if proxy_id and proxy_id in parsed.data_ids:
                    image_id = proxy_id
                else:
                    errors.append(f"{href}: image {src or '<no src>'} has no data-id or narrated proxy")
                    continue
            mapped_ids.add(image_id)
            if not src:
                errors.append(f"{href}: {image_id} has no src")
            elif not (ROOT / src).is_file():
                errors.append(f"{href}: {image_id} references missing image {src}")
            if not alt:
                errors.append(f"{href}: {image_id} has empty alt text")
            if not str(texts.get(image_id, "")).strip():
                errors.append(f"{href}: {image_id} has no nonempty texts.json entry")
            filename = audios.get(image_id, "")
            if not filename:
                errors.append(f"{href}: {image_id} has no audios.json mapping")
                continue
            audio_path = LANG_DIR / "audio" / filename
            mp3_paths.add(audio_path)
            if not audio_path.is_file() or audio_path.stat().st_size == 0:
                errors.append(f"{href}: {image_id} maps to missing or empty {filename}")

            easy_id = f"{image_id}_easy_read"
            if easy_id in texts and texts[easy_id] != texts.get(image_id):
                easy_filename = audios.get(easy_id, "")
                if not easy_filename:
                    errors.append(f"{href}: changed Easy Read image {easy_id} has no audio mapping")
                else:
                    easy_path = LANG_DIR / "audio" / easy_filename
                    mp3_paths.add(easy_path)
                    if not easy_path.is_file() or easy_path.stat().st_size == 0:
                        errors.append(f"{href}: {easy_id} maps to missing or empty {easy_filename}")

    if not args.skip_ffprobe:
        if not shutil.which("ffprobe"):
            errors.append("ffprobe is required unless --skip-ffprobe is supplied")
        else:
            with ThreadPoolExecutor(max_workers=8) as executor:
                for result in executor.map(probe_mp3, sorted(mp3_paths)):
                    if result:
                        errors.append(result)

    if errors:
        print(f"FAIL: {len(errors)} image read-aloud issue(s)", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    probe_status = "structurally checked" if args.skip_ffprobe else "ffprobe-validated"
    print(
        "PASS: "
        f"{len(pages)} manifest pages, {image_occurrences} image occurrences, "
        f"{len(mapped_ids)} image IDs, and {len(mp3_paths)} {probe_status} MP3 files; "
        f"bundle version {bundle_version} enables image narration before runtime boot."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
