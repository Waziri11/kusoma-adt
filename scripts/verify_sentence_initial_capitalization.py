#!/usr/bin/env python3
"""Verify the complete sentence-initial capitalization correction."""

from __future__ import annotations

import html
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "content" / "i18n" / "sw-TZ"
REPORT = json.loads(
    (ROOT / "reports" / "sentence-initial-capitalization-audit.json").read_text(
        encoding="utf-8"
    )
)
TEXTS = json.loads((I18N / "texts.json").read_text(encoding="utf-8"))
AUDIOS = json.loads((I18N / "audios.json").read_text(encoding="utf-8"))
CONFIG = json.loads((ROOT / "assets" / "config.json").read_text(encoding="utf-8"))
VERSION = str(CONFIG.get("bundleVersion", ""))
LOWERCASE_QUESTION = re.compile(r"^((?:\d+\.\s+)?)sauti au herufi\b")
ALPHABETIC = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")
INTERNAL_PATTERNS = (
    re.compile(r"(?<=[.!?])\s+[“\"'\(\[]*([a-zà-öø-ÿ])"),
    re.compile(r"\n\s*(?:[-*]\s*)?[“\"'\(\[]*([a-zà-öø-ÿ])"),
)


if REPORT["standard_count"] != 34 or REPORT["easy_read_count"] != 20:
    raise RuntimeError("Capitalization report target counts changed")
if REPORT["total_count"] != 54 or len(REPORT["changes"]) != 54:
    raise RuntimeError("Capitalization report does not contain all 54 changes")
if not VERSION.isdigit():
    raise RuntimeError("assets/config.json has an invalid bundleVersion")

remaining = [
    text_id
    for text_id, value in TEXTS.items()
    if isinstance(value, str) and LOWERCASE_QUESTION.search(value)
]
if remaining:
    raise RuntimeError(f"Lowercase repeated questions remain: {remaining}")


def signature(entries: list[dict[str, str]]) -> list[tuple[str, str]]:
    return [(entry["text_id"], entry["text"]) for entry in entries]


current_leading: list[tuple[str, str]] = []
current_short_terminal: list[tuple[str, str]] = []
current_internal: list[tuple[str, str]] = []
current_glossary: list[tuple[str, str]] = []
current_answers: list[tuple[str, str]] = []
for text_id, value in TEXTS.items():
    if not isinstance(value, str) or not value.strip():
        continue
    stripped = value.strip()
    first_alpha = ALPHABETIC.search(stripped)
    if first_alpha and first_alpha.group().islower():
        row = (text_id, stripped)
        if text_id.startswith("gl"):
            current_glossary.append(row)
        elif "_ans_" in text_id:
            current_answers.append(row)
        elif len(stripped.split()) >= 3:
            current_leading.append(row)
        elif re.search(r"[.!?][”'\"]?$", stripped):
            current_short_terminal.append(row)
    if any(pattern.search(value) for pattern in INTERNAL_PATTERNS):
        current_internal.append((text_id, stripped))

audit = REPORT["complete_lowercase_audit"]
reviewed_sets = (
    (
        "reviewed_lowercase_multiword_candidates",
        current_leading,
    ),
    (
        "reviewed_short_terminal_candidates",
        current_short_terminal,
    ),
    (
        "reviewed_internal_or_newline_candidates",
        current_internal,
    ),
    (
        "glossary_headwords_and_definition_fragments",
        current_glossary,
    ),
    (
        "activity_answer_or_technical_values",
        current_answers,
    ),
)
for report_key, current in reviewed_sets:
    expected = signature(audit[report_key])
    if current != expected:
        raise RuntimeError(f"Whole-book lowercase audit drift in {report_key}")

audio_files: list[Path] = []
for change in REPORT["changes"]:
    text_id = change["text_id"]
    expected_text = change["new_text"]
    expected_audio = change["audio"]
    if change.get("audio_unchanged") is not True:
        raise RuntimeError(f"Capitalization-only audio policy missing for {text_id}")
    if TEXTS.get(text_id) != expected_text:
        raise RuntimeError(f"Text mismatch for {text_id}")
    if AUDIOS.get(text_id) != expected_audio:
        raise RuntimeError(f"Audio mapping mismatch for {text_id}")
    audio_path = I18N / "audio" / expected_audio
    if not audio_path.is_file() or audio_path.stat().st_size == 0:
        raise RuntimeError(f"Missing or empty audio for {text_id}: {audio_path.name}")
    audio_files.append(audio_path)

    if not text_id.endswith("_easy_read"):
        page = ROOT / f"{text_id[:5]}_sec001.html"
        source = page.read_text(encoding="utf-8")
        match = re.search(
            rf'<[^>]+\bdata-id="{re.escape(text_id)}"[^>]*>([^<]*)</[^>]+>',
            source,
        )
        if not match:
            raise RuntimeError(f"Missing HTML fallback for {text_id}")
        if html.unescape(match.group(1)).strip() != expected_text:
            raise RuntimeError(f"HTML/texts.json mismatch for {text_id}")

html_files = sorted(ROOT.glob("*.html"))
if len(html_files) != 104:
    raise RuntimeError(f"Expected 104 root HTML files, found {len(html_files)}")
for page in html_files:
    source = page.read_text(encoding="utf-8")
    for asset in (
        f"./assets/offline-preloader.js?v={VERSION}",
        f"./assets/image-description-default.js?v={VERSION}",
        f"./assets/base.bundle.local.js?v={VERSION}",
    ):
        if asset not in source:
            raise RuntimeError(f"{page.name} lacks {asset}")
    asset_versions = set(
        re.findall(
            r"(?:offline-preloader|image-description-default|base\.bundle\.local)\.js\?v=(\d+)",
            source,
        )
    )
    if asset_versions != {VERSION}:
        raise RuntimeError(
            f"Mixed shared-asset versions in {page.name}: {sorted(asset_versions)}"
        )

preloader = (ROOT / "assets" / "offline-preloader.js").read_text(encoding="utf-8")
if f'"bundleVersion":"{VERSION}"' not in preloader:
    raise RuntimeError(
        f"Offline preloader does not embed bundleVersion {VERSION}"
    )
for change in REPORT["changes"]:
    if json.dumps(change["new_text"], ensure_ascii=False) not in preloader:
        raise RuntimeError(f"Offline preloader lacks text for {change['text_id']}")
    if change["audio"] not in preloader:
        raise RuntimeError(f"Offline preloader lacks audio mapping for {change['text_id']}")

for audio_path in audio_files:
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    if float(probe.stdout.strip()) <= 0:
        raise RuntimeError(f"Nonpositive audio duration: {audio_path.name}")
    volume = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(audio_path), "-af", "volumedetect", "-f", "null", "-"],
        check=True,
        capture_output=True,
        text=True,
    )
    match = re.search(r"mean_volume:\s*(-?[0-9.]+) dB", volume.stderr)
    if not match or float(match.group(1)) <= -80:
        raise RuntimeError(f"Silent or unmeasurable audio: {audio_path.name}")

print(
    "PASS: 54 sentence starts capitalized (34 standard, 20 Easy Read), "
    "34 HTML fallbacks synchronized, 54 retained signaled RehemaNeural MP3s valid, "
    "all remaining sentence-like lowercase candidates match the reviewed audit, "
    f"and all 104 pages/preloader are cache-versioned at v{VERSION}."
)
