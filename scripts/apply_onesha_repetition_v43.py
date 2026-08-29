#!/usr/bin/env python3
"""Apply the approved Onesha and repeated-herufi corrections for bundle v43."""

from __future__ import annotations

import argparse
import html
from html.parser import HTMLParser
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LANG = ROOT / "content" / "i18n" / "sw-TZ"
TEXTS_PATH = LANG / "texts.json"
MATRIX_PATH = ROOT / "reports" / "onesha-repetition-correction-matrix-v43.json"
VERSION = "43"

TARGET_BASE_IDS = {
    "pg031_n0007",
    "pg032_n0002",
    "pg033_n0029",
    "pg036_n0027",
    "pg039_n0012",
    "pg042_n0003", "pg042_n0009",
    "pg043_n0003",
    "pg046_n0003",
    "pg047_n0003",
    "pg049_n0003",
    "pg050_n0005",
    "pg052_n0010",
    "pg053_n0019",
    "pg056_n0003",
    "pg057_n0003",
    "pg059_n0012",
    "pg060_n0017",
    "pg062_n0011",
    "pg063_n0017",
    "pg065_n0019",
    "pg066_n0032",
    "pg068_n0020",
    "pg070_n0022",
    "pg072_n0024",
    "pg075_n0027",
    "pg078_n0032",
    "pg081_n0003",
    "pg083_n0021",
}


def transform(base_id: str, value: str, *, easy_read: bool) -> str:
    if base_id == "pg031_n0007":
        expected = "Onesha na tamka / bainisha sauti ya herufi l."
        if value not in {expected, "Onesha na tamka sauti ya herufi l."}:
            raise RuntimeError(f"{base_id}: unexpected page 31 wording: {value!r}")
        return "Onesha na tamka sauti ya herufi l."

    if base_id == "pg042_n0009":
        if easy_read:
            expected = "Onesha herufi g.\nKisha tamka / bainisha herufi yake."
            fixed = "Onesha herufi g.\nKisha tamka sauti yake."
        else:
            expected = "Onesha na tamka / bainisha herufi ya herufi g."
            fixed = "Onesha na tamka sauti ya herufi g."
        if value not in {expected, fixed}:
            raise RuntimeError(f"{base_id}: unexpected page 42 Onesha wording: {value!r}")
        return fixed

    for old, new in (
        ("herufi ya herufi", "sauti ya herufi"),
        ("herufi za herufi", "sauti za herufi"),
    ):
        if old in value:
            return value.replace(old, new, 1)
        if new in value:
            return value
    raise RuntimeError(f"{base_id}: no repeated-herufi construction: {value!r}")


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def plain_text(fragment: str) -> str:
    parser = TextExtractor()
    parser.feed(fragment)
    return re.sub(r"\s+", " ", "".join(parser.parts)).strip()


def update_html(text_id: str, old: str, new: str, *, verify: bool) -> None:
    page = ROOT / f"{text_id.split('_', 1)[0]}_sec001.html"
    source = page.read_text(encoding="utf-8")
    pattern = re.compile(
        rf'(<(?P<tag>[a-zA-Z][\w:-]*)\b[^>]*\bdata-id="{re.escape(text_id)}"[^>]*>)'
        rf'(?P<body>.*?)(</(?P=tag)>)',
        re.DOTALL,
    )
    match = pattern.search(source)
    if not match:
        raise RuntimeError(f"{page.name}: missing HTML element for {text_id}")
    current = plain_text(match.group("body"))
    expected_old = re.sub(r"\s+", " ", old).strip()
    expected_new = re.sub(r"\s+", " ", new).strip()
    if current not in {expected_old, expected_new}:
        raise RuntimeError(
            f"{page.name}: {text_id} HTML drift: {current!r}; "
            f"expected {expected_old!r} or {expected_new!r}"
        )
    if verify:
        if current != expected_new:
            raise RuntimeError(f"{page.name}: {text_id} was not updated")
        return
    rendered = html.escape(new, quote=False).replace("\n", "<br>")
    replacement = match.group(1) + rendered + match.group(4)
    page.write_text(
        source[: match.start()] + replacement + source[match.end() :],
        encoding="utf-8",
    )


def build_or_load_matrix(texts: dict[str, str]) -> dict[str, object]:
    if MATRIX_PATH.exists():
        return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    corrections = []
    for base_id in sorted(TARGET_BASE_IDS):
        normal_old = texts.get(base_id)
        easy_id = f"{base_id}_easy_read"
        easy_old = texts.get(easy_id)
        if not isinstance(normal_old, str) or not normal_old.strip():
            raise RuntimeError(f"{base_id}: missing normal text")
        if not isinstance(easy_old, str) or not easy_old.strip():
            raise RuntimeError(f"{easy_id}: missing Easy Read text")
        corrections.append(
            {
                "base_id": base_id,
                "page": int(base_id[2:5]),
                "normal": {
                    "text_id": base_id,
                    "expected_old": normal_old,
                    "expected_new": transform(base_id, normal_old, easy_read=False),
                },
                "easy_read": {
                    "text_id": easy_id,
                    "expected_old": easy_old,
                    "expected_new": transform(base_id, easy_old, easy_read=True),
                },
            }
        )
    matrix = {
        "version": 43,
        "stable_base_id_count": len(TARGET_BASE_IDS),
        "text_entry_count": len(TARGET_BASE_IDS) * 2,
        "corrections": corrections,
    }
    MATRIX_PATH.parent.mkdir(parents=True, exist_ok=True)
    MATRIX_PATH.write_text(
        json.dumps(matrix, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return matrix


def update_cache_version(*, verify: bool) -> None:
    config_path = ROOT / "assets" / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if str(config.get("bundleVersion")) not in {"42", VERSION}:
        raise RuntimeError(f"Unexpected starting bundleVersion: {config.get('bundleVersion')}")
    html_files = sorted(ROOT.glob("*.html"))
    if len(html_files) != 104:
        raise RuntimeError(f"Expected 104 root HTML files, found {len(html_files)}")
    if verify:
        if str(config.get("bundleVersion")) != VERSION:
            raise RuntimeError(f"assets/config.json is not bundleVersion {VERSION}")
        for page in html_files:
            source = page.read_text(encoding="utf-8")
            for asset in (
                "offline-preloader.js", "image-description-default.js", "base.bundle.local.js"
            ):
                if f"./assets/{asset}?v={VERSION}" not in source:
                    raise RuntimeError(f"{page.name}: missing v{VERSION} query for {asset}")
        return
    config["bundleVersion"] = VERSION
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for page in html_files:
        source = page.read_text(encoding="utf-8")
        page.write_text(source.replace("?v=42", f"?v={VERSION}"), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    texts: dict[str, str] = json.loads(TEXTS_PATH.read_text(encoding="utf-8"))
    matrix = build_or_load_matrix(texts)
    rows = matrix.get("corrections", [])
    if {row["base_id"] for row in rows} != TARGET_BASE_IDS:
        raise RuntimeError("Correction matrix target set drift")

    updates: dict[str, str] = {}
    for row in rows:
        base_id = row["base_id"]
        for entry_name in ("normal", "easy_read"):
            entry = row[entry_name]
            text_id = entry["text_id"]
            current = texts.get(text_id)
            if current not in {entry["expected_old"], entry["expected_new"]}:
                raise RuntimeError(f"{text_id}: texts.json drift: {current!r}")
            updates[text_id] = entry["expected_new"]
        update_html(
            base_id,
            row["normal"]["expected_old"],
            row["normal"]["expected_new"],
            verify=args.verify,
        )

    if args.verify:
        for text_id, expected in updates.items():
            if texts.get(text_id) != expected:
                raise RuntimeError(f"{text_id}: texts.json was not updated")
        update_cache_version(verify=True)
        print("PASS: 29 normal and 29 Easy Read Onesha/repetition corrections verified")
        return

    texts.update(updates)
    TEXTS_PATH.write_text(
        json.dumps(texts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    update_cache_version(verify=False)
    print("Applied 29 normal and 29 Easy Read corrections; bundleVersion 43")


if __name__ == "__main__":
    main()
