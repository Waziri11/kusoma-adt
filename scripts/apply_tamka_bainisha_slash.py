#!/usr/bin/env python3
"""Apply the approved whole-book Tamka / bainisha wording correction."""

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
MATRIX_PATH = ROOT / "reports" / "tamka-bainisha-correction-matrix-v42.json"
VERSION = "42"

TARGET_BASE_IDS = {
    "pg012_n0005",
    "pg013_n0008", "pg013_n0032", "pg013_n0040",
    "pg014_n0017", "pg014_n0025", "pg014_n0050",
    "pg015_n0008", "pg015_n0033", "pg015_n0041",
    "pg016_n0006", "pg016_n0011",
    "pg017_n0017", "pg017_n0023",
    "pg019_n0044", "pg019_n0050",
    "pg020_n0031",
    "pg021_n0019", "pg021_n0027",
    "pg022_n0035",
    "pg023_n0080",
    "pg024_n0003", "pg024_n0042",
    "pg025_n0083",
    "pg026_n0005",
    "pg027_n0009",
    "pg030_n0016", "pg030_n0023",
    "pg032_n0002", "pg032_n0084",
    "pg033_n0029",
    "pg035_n0010",
    "pg036_n0027",
    "pg038_n0006",
    "pg039_n0012",
    "pg041_n0015", "pg041_n0020",
    "pg042_n0003", "pg042_n0009",
    "pg043_n0003",
    "pg045_n0008",
    "pg046_n0003",
    "pg047_n0003",
    "pg048_n0008",
    "pg049_n0003",
    "pg050_n0005",
    "pg051_n0014",
    "pg052_n0010",
    "pg053_n0019",
    "pg055_n0016", "pg055_n0022",
    "pg056_n0003",
    "pg057_n0003",
    "pg058_n0014",
    "pg059_n0012",
    "pg060_n0017",
    "pg062_n0002", "pg062_n0011",
    "pg063_n0017",
    "pg065_n0007", "pg065_n0019",
    "pg066_n0032",
    "pg067_n0016", "pg067_n0023",
    "pg068_n0020",
    "pg069_n0068",
    "pg070_n0022",
    "pg071_n0029",
    "pg072_n0003", "pg072_n0024",
    "pg074_n0011", "pg074_n0020",
    "pg075_n0027",
    "pg077_n0009", "pg077_n0016",
    "pg078_n0032",
    "pg079_n0065",
    "pg080_n0005",
    "pg081_n0003",
    "pg082_n0006", "pg082_n0012",
    "pg083_n0021",
    "pg090_n0035",
}

DIRECT_PATTERN = re.compile(
    r"\b(?P<verb>Tamka|tamka|Sema|sema)\s+sauti\s+au\s+bainisha\s+herufi\b"
)
REVERSED_PATTERN = re.compile(
    r"\b(?P<verb>Tamka|tamka|Sema|sema)\s+au\s+bainisha\b"
)
MALFORMED_SLASH_PATTERN = re.compile(
    r"\b(?P<verb>Tamka|tamka|Sema|sema)/\s*bainisha\b"
)


def transform(text_id: str, value: str) -> str:
    for pattern in (DIRECT_PATTERN, REVERSED_PATTERN, MALFORMED_SLASH_PATTERN):
        updated, count = pattern.subn(
            lambda match: f"{match.group('verb')} / bainisha"
            + (" herufi" if pattern is DIRECT_PATTERN else ""),
            value,
            count=1,
        )
        if count == 1:
            return updated
    if " / bainisha" in value:
        return value
    raise RuntimeError(f"{text_id}: no approved Tamka/Sema alternative form: {value!r}")


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
                    "expected_new": transform(base_id, normal_old),
                },
                "easy_read": {
                    "text_id": easy_id,
                    "expected_old": easy_old,
                    "expected_new": transform(easy_id, easy_old),
                },
            }
        )
    matrix = {
        "version": 42,
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
    if str(config.get("bundleVersion")) not in {"40", "41", VERSION}:
        raise RuntimeError(f"Unexpected starting bundleVersion: {config.get('bundleVersion')}")
    html_files = sorted(ROOT.glob("*.html"))
    if len(html_files) != 104:
        raise RuntimeError(f"Expected 104 root HTML files, found {len(html_files)}")
    if verify:
        if str(config.get("bundleVersion")) != VERSION:
            raise RuntimeError(f"assets/config.json is not bundleVersion {VERSION}")
        for page in html_files:
            source = page.read_text(encoding="utf-8")
            if "?v=40" in source or "?v=41" in source:
                raise RuntimeError(f"{page.name}: stale cache query")
        return
    config["bundleVersion"] = VERSION
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for page in html_files:
        source = page.read_text(encoding="utf-8")
        updated = source.replace("?v=40", f"?v={VERSION}").replace(
            "?v=41", f"?v={VERSION}"
        )
        page.write_text(updated, encoding="utf-8")


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
        for entry_name in ("normal", "easy_read"):
            entry = row[entry_name]
            text_id = entry["text_id"]
            current = texts.get(text_id)
            if current not in {entry["expected_old"], entry["expected_new"]}:
                raise RuntimeError(f"{text_id}: texts.json drift: {current!r}")
            updates[text_id] = entry["expected_new"]
        update_html(
            row["base_id"],
            row["normal"]["expected_old"],
            row["normal"]["expected_new"],
            verify=args.verify,
        )

    if args.verify:
        for text_id, expected in updates.items():
            if texts.get(text_id) != expected:
                raise RuntimeError(f"{text_id}: texts.json was not updated")
        update_cache_version(verify=True)
        print("PASS: 83 normal and 83 Easy Read slash corrections verified")
        return

    texts.update(updates)
    TEXTS_PATH.write_text(
        json.dumps(texts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    update_cache_version(verify=False)
    print("Applied 83 normal and 83 Easy Read slash corrections; bundleVersion 42")


if __name__ == "__main__":
    main()
