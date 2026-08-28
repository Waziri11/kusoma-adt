#!/usr/bin/env python3
"""Apply the approved additional Kusoma editorial corrections.

The target lists are intentionally explicit.  Each transformation validates
the current wording before changing it so that a later rerun cannot silently
rewrite unrelated content.
"""

from __future__ import annotations

import argparse
import html
from html.parser import HTMLParser
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXTS_PATH = ROOT / "content" / "i18n" / "sw-TZ" / "texts.json"
MATRIX_PATH = ROOT / "reports" / "additional-feedback-correction-matrix-v28.json"


TAJA_IDS = {
    "pg010_n0009",
    "pg013_n0006", "pg013_n0038",
    "pg014_n0023",
    "pg015_n0006", "pg015_n0039",
}

PHRASE_IDS = {
    "pg012_n0005",
    "pg013_n0008", "pg013_n0032", "pg013_n0040",
    "pg014_n0017", "pg014_n0025", "pg014_n0050",
    "pg015_n0008", "pg015_n0033", "pg015_n0041",
    "pg016_n0006", "pg016_n0011",
    "pg017_n0017", "pg017_n0023",
    "pg019_n0044", "pg019_n0050",
    "pg021_n0019", "pg021_n0027",
    "pg023_n0080",
    "pg024_n0003",
    "pg025_n0083",
    "pg026_n0005",
    "pg027_n0009",
    "pg030_n0016", "pg030_n0023",
    "pg031_n0003", "pg031_n0007",
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
}

SOUND_OR_LETTER_IDS = {
    "pg012_n0008", "pg012_n0011",
    "pg017_n0019", "pg017_n0025", "pg017_n0027",
    "pg019_n0046", "pg019_n0052", "pg019_n0054",
    "pg021_n0021", "pg021_n0029", "pg021_n0031",
    "pg026_n0007", "pg026_n0009",
    "pg030_n0018", "pg030_n0025", "pg030_n0027",
    "pg032_n0086", "pg033_n0005", "pg033_n0007",
    "pg035_n0012", "pg036_n0004", "pg036_n0007",
    "pg038_n0008", "pg038_n0012", "pg038_n0014",
    "pg041_n0017", "pg041_n0022", "pg041_n0024",
    "pg045_n0011", "pg045_n0017", "pg045_n0020",
    "pg048_n0011", "pg048_n0017", "pg048_n0020",
    "pg051_n0017", "pg052_n0004", "pg052_n0007",
    "pg055_n0018", "pg055_n0024", "pg055_n0026",
    "pg058_n0015", "pg059_n0006", "pg059_n0009",
    "pg062_n0003", "pg062_n0007", "pg062_n0008",
    "pg065_n0009", "pg065_n0014", "pg065_n0016",
    "pg067_n0018", "pg067_n0025", "pg067_n0027",
    "pg069_n0070", "pg069_n0078", "pg069_n0080",
    "pg071_n0031", "pg072_n0005", "pg072_n0007",
    "pg074_n0013", "pg074_n0022", "pg074_n0024",
    "pg077_n0010", "pg077_n0017", "pg077_n0018",
    "pg079_n0067", "pg080_n0007", "pg080_n0009",
    "pg082_n0008", "pg082_n0014", "pg082_n0016",
}

INTRO_IDS = {
    "pg017_n0010", "pg030_n0009", "pg041_n0009",
    "pg055_n0009", "pg067_n0009",
}

CUSTOM_NORMAL = {
    "pg011_n0017": "Taja majina au bainisha matendo ya picha hizi.",
    "pg018_n0005": "Onesha au tamka sauti ya herufi b.",
    "pg090_n0035": "2. Tamka au bainisha silabi za mwisho zinazounda maneno hayo.",
    "pg090_n0037": "Zitamke na zisome.",
}

CUSTOM_EASY = {
    "pg011_n0017": "Taja majina au bainisha matendo ya picha hizi.",
    "pg018_n0005": "Onesha sauti ya herufi b.\nAu itamke.",
    "pg090_n0035": "2. Tamka au bainisha silabi za mwisho za maneno hayo.",
    "pg090_n0037": "Zitamke na zisome.",
}

CHANGED_BASE_IDS = (
    TAJA_IDS | PHRASE_IDS | SOUND_OR_LETTER_IDS | INTRO_IDS | set(CUSTOM_NORMAL)
)


def replace_once(value: str, pattern: str, replacement: str, text_id: str) -> str:
    updated, count = re.subn(pattern, replacement, value, count=1, flags=re.IGNORECASE)
    if count != 1:
        raise RuntimeError(f"{text_id}: expected one match for {pattern!r}: {value!r}")
    return updated


def transform(text_id: str, value: str, *, easy: bool) -> str:
    if text_id in CUSTOM_NORMAL:
        return (CUSTOM_EASY if easy else CUSTOM_NORMAL)[text_id]
    if text_id in TAJA_IDS:
        if "Taja au bainisha" in value:
            return value
        return replace_once(value, r"\bTaja\s+", "Taja au bainisha ", text_id)
    if text_id in PHRASE_IDS:
        if "bainisha herufi" in value:
            return value
        if re.search(r"\b[Tt]amka\s+sauti\b", value):
            return replace_once(
                value,
                r"\b([Tt]amka)\s+sauti\b",
                r"\1 sauti au bainisha herufi",
                text_id,
            )
        if re.search(r"\bTaja\s+sauti\b", value):
            return replace_once(
                value,
                r"\bTaja\s+sauti\b",
                "Tamka sauti au bainisha herufi",
                text_id,
            )
        if re.search(r"\bSema\s+sauti\b", value):
            return replace_once(
                value,
                r"\bSema\s+sauti\b",
                "Sema sauti au bainisha herufi",
                text_id,
            )
        raise RuntimeError(f"{text_id}: no Tamka/Taja/Sema sauti phrase: {value!r}")
    if text_id in SOUND_OR_LETTER_IDS:
        if "sauti au herufi" in value:
            return value
        return replace_once(value, r"\bsauti\b", "sauti au herufi", text_id)
    if text_id in INTRO_IDS:
        if "kubainisha" in value:
            return value
        if "kuzitamka" in value:
            return value.replace("kuzitamka,", "kuzitamka, kubainisha,", 1)
        if "kutamka sauti hizi" in value:
            return value.replace(
                "kutamka sauti hizi", "kutamka na kubainisha sauti hizi", 1
            )
        raise RuntimeError(f"{text_id}: no chapter-introduction anchor: {value!r}")
    raise KeyError(text_id)


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


def update_html_fallback(text_id: str, old: str, new: str, *, verify: bool) -> None:
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
    page.write_text(source[: match.start()] + replacement + source[match.end() :], encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    texts: dict[str, str] = json.loads(TEXTS_PATH.read_text(encoding="utf-8"))
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    matrix_rows = {row["base_id"]: row for row in matrix["corrections"]}
    if set(matrix_rows) != CHANGED_BASE_IDS:
        raise RuntimeError("Correction matrix ID set does not match the scripted target set")
    updates: dict[str, str] = {}
    expected_old: dict[str, str] = {}
    for text_id in sorted(CHANGED_BASE_IDS):
        old = texts.get(text_id)
        if not isinstance(old, str) or not old.strip():
            raise RuntimeError(f"{text_id}: missing nonempty normal text")
        normal_row = matrix_rows[text_id]["normal"]
        expected_old[text_id] = normal_row["expected_old"]
        updates[text_id] = normal_row["expected_new"]
        if old not in {expected_old[text_id], updates[text_id]}:
            raise RuntimeError(f"{text_id}: normal text drift: {old!r}")
        if transform(text_id, expected_old[text_id], easy=False) != updates[text_id]:
            raise RuntimeError(f"{text_id}: normal matrix transformation drift")
        easy_id = f"{text_id}_easy_read"
        easy_old = texts.get(easy_id)
        if isinstance(easy_old, str) and easy_old.strip():
            easy_row = matrix_rows[text_id].get("easy_read")
            if not easy_row or easy_row.get("text_id") != easy_id:
                raise RuntimeError(f"{easy_id}: missing correction matrix row")
            expected_old[easy_id] = easy_row["expected_old"]
            updates[easy_id] = easy_row["expected_new"]
            if easy_old not in {expected_old[easy_id], updates[easy_id]}:
                raise RuntimeError(f"{easy_id}: Easy Read text drift: {easy_old!r}")
            if transform(text_id, expected_old[easy_id], easy=True) != updates[easy_id]:
                raise RuntimeError(f"{easy_id}: Easy Read matrix transformation drift")

    if any("bainsiha" in value.lower() for value in updates.values()):
        raise RuntimeError("Correction matrix contains the misspelling 'bainsiha'")

    for text_id in sorted(CHANGED_BASE_IDS):
        update_html_fallback(
            text_id,
            expected_old[text_id],
            updates[text_id],
            verify=args.verify,
        )

    if args.verify:
        for text_id, expected in updates.items():
            if texts.get(text_id) != expected:
                raise RuntimeError(f"{text_id}: texts.json was not updated")
        print(f"PASS: {len(updates)} normal/Easy Read correction entries verified")
        return

    texts.update(updates)
    TEXTS_PATH.write_text(
        json.dumps(texts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Applied {len(updates)} normal/Easy Read entries across "
        f"{len(CHANGED_BASE_IDS)} stable base IDs."
    )


if __name__ == "__main__":
    main()
