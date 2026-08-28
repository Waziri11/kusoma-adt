#!/usr/bin/env python3
"""Use concise names, not visual descriptions, for phonics prompt images.

These targets are the complete book-wide set where either the authored HTML
already supplied a concise teaching name but localization replaced it with a
description, or the reported page has a visible word label immediately after
the image. Letter grids are handled separately by fix_sound_grid_narration.py.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Tuple

from fix_all_letter_sound_audio import VOICE, probe_audio, synthesize_unit


ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "content" / "i18n" / "sw-TZ"
OUTPUT_SUFFIX = "name_only_v26"
Segment = Tuple[str, str]

TARGETS: Dict[str, str] = {
    "pg021_im001": "Kuku",
    "pg021_im002": "Kinyonga",
    "pg021_im004": "Kobe",
    "pg034_im001": "Moto",
    "pg034_im002": "Bata",
    "pg035_im001": "Noti",
    "pg040_im004": "Sumu",
    "pg040_im006": "Pesa",
    "pg040_im005": "Pesa",
    "pg040_im007": "Pesa",
    "pg040_im003": "Saa",
    "pg040_im002": "Leso",
    "pg040_im001": "Simu",
    "pg040_im008": "Samaki",
    "pg044_im003": "Gogo",
    "pg044_im006": "Mtego",
    "pg044_im001": "Boga",
    "pg044_im004": "Gololi",
    "pg044_im002": "Gauni",
    "pg044_im005": "Gunia",
    "pg045_im001": "Yai",
    "pg045_im003": "Jiko la moto",
    "pg045_im004": "Korongo",
    "pg045_im002": "Yai",
    "pg048_im001": "Zipu",
    "pg048_im002_seg001_v1": "Tikiti maji",
    "pg048_im004": "Zabibu",
    "pg048_im003": "Zambarau",
    "pg048_im002_seg002_v1_crop_v1": "Kipande cha tikiti maji",
    "pg050_im002": "Zeze",
    "pg050_im001": "Uzi",
    "pg052_im002": "Hereni",
    "pg052_im001": "Mahindi",
    "pg052_im003_crop_v1": "Jicho",
    "pg054_im002": "Hoho",
    "pg054_im003": "Hela",
    "pg054_im004": "Hela",
    "pg054_im005": "Hela",
    "pg054_im001": "Hema",
    "pg058_im002": "Reli",
    "pg058_im003": "Ruka",
    "pg058_im004": "Rula",
    "pg058_im001": "Raba",
    "pg058_im005": "Wembe",
    "pg059_im001": "Watu",
    "pg062_im001": "Vijiko",
    "pg062_im006": "Sahani",
    "pg073_im001": "Mbuzi",
    "pg073_im002": "Simba",
    "pg074_im001": "Mbuni",
    "pg074_im002": "Tembo",
    "pg074_im005": "Nyoka",
    "pg074_im003": "Kengele",
    "pg074_im006": "Nyani",
    "pg074_im004": "Nyumba",
    "pg076_im001": "Nyoka",
    "pg076_im002": "Panya",
    "pg076_im004": "Nyota",
    "pg076_im003": "Unyoya",
    "pg077_im002": "Nyuki",
    "pg077_im001": "Nyani",
    "pg077_im004": "Ngoma",
    "pg077_im006": "Kiti",
    "pg077_im005": "Ngoma",
    "pg077_im003": "Ngazi",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--retries", type=int, default=6)
    return parser.parse_args()


def current_html_targets() -> Dict[str, Path]:
    found: Dict[str, Path] = {}
    for page in ROOT.glob("*.html"):
        source = page.read_text(encoding="utf-8")
        for text_id in TARGETS:
            if re.search(
                rf"<img\b[^>]*\bdata-id=(?:\"{re.escape(text_id)}\"|'{re.escape(text_id)}')",
                source,
                re.IGNORECASE,
            ):
                if text_id in found:
                    raise RuntimeError(f"{text_id} occurs on more than one page")
                found[text_id] = page
    missing = sorted(set(TARGETS) - set(found))
    if missing:
        raise RuntimeError(f"Target images missing from HTML: {', '.join(missing)}")
    return found


def replace_alt(source: str, text_id: str, value: str) -> str:
    image_pattern = re.compile(
        rf"<img\b[^>]*\bdata-id=(?:\"{re.escape(text_id)}\"|'{re.escape(text_id)}')[^>]*>",
        re.IGNORECASE,
    )
    matches = list(image_pattern.finditer(source))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one image element for {text_id}, found {len(matches)}")
    tag = matches[0].group(0)
    escaped = html.escape(value, quote=True)
    if re.search(r"\balt\s*=", tag, re.IGNORECASE):
        updated = re.sub(
            r"\balt\s*=\s*(?:\"[^\"]*\"|'[^']*')",
            f'alt="{escaped}"',
            tag,
            count=1,
            flags=re.IGNORECASE,
        )
    else:
        updated = tag[:-1] + f' alt="{escaped}">'
    return source[: matches[0].start()] + updated + source[matches[0].end() :]


def signal_levels(path: Path) -> Dict[str, float]:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    mean_match = re.search(r"mean_volume:\s*(-?[0-9.]+) dB", result.stderr)
    max_match = re.search(r"max_volume:\s*(-?[0-9.]+) dB", result.stderr)
    if not mean_match or not max_match:
        raise RuntimeError(f"Could not measure signal levels: {path}")
    levels = {
        "mean_volume_db": float(mean_match.group(1)),
        "max_volume_db": float(max_match.group(1)),
    }
    if levels["max_volume_db"] < -45:
        raise RuntimeError(f"Generated audio is effectively silent: {path}")
    return levels


def verify(texts: dict, audios: dict, html_targets: Dict[str, Path]) -> list:
    results = []
    for text_id, name in TARGETS.items():
        if texts.get(text_id) != name:
            raise RuntimeError(f"Unexpected text for {text_id}: {texts.get(text_id)!r}")
        expected_filename = f"{text_id}_{OUTPUT_SUFFIX}.mp3"
        if audios.get(text_id) != expected_filename:
            raise RuntimeError(f"Unexpected mapping for {text_id}: {audios.get(text_id)!r}")
        source = html_targets[text_id].read_text(encoding="utf-8")
        image_match = re.search(
            rf"<img\b[^>]*\bdata-id=(?:\"{re.escape(text_id)}\"|'{re.escape(text_id)}')[^>]*>",
            source,
            re.IGNORECASE,
        )
        alt_match = re.search(r"\balt\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", image_match.group(0), re.I)
        actual_alt = html.unescape((alt_match.group(1) or alt_match.group(2)) if alt_match else "")
        if actual_alt != name:
            raise RuntimeError(f"Unexpected HTML alt for {text_id}: {actual_alt!r}")
        audio_path = I18N / "audio" / expected_filename
        results.append(
            {
                "text_id": text_id,
                "page": html_targets[text_id].name,
                "spoken_name": name,
                "audio_filename": expected_filename,
                **probe_audio(audio_path),
                **signal_levels(audio_path),
            }
        )
    return results


async def main() -> None:
    args = parse_args()
    texts_path = I18N / "texts.json"
    audios_path = I18N / "audios.json"
    texts = json.loads(texts_path.read_text(encoding="utf-8"))
    audios = json.loads(audios_path.read_text(encoding="utf-8"))
    html_targets = current_html_targets()

    if not args.verify_only:
        units = {name: ("prose", name) for name in set(TARGETS.values())}
        with tempfile.TemporaryDirectory(prefix="kusoma-phonics-names-") as name:
            stage = Path(name)
            generated_units = {
                name: stage / f"name_{index:03d}.mp3"
                for index, name in enumerate(sorted(units), start=1)
            }
            semaphore = asyncio.Semaphore(args.concurrency)
            await asyncio.gather(
                *(
                    synthesize_unit(
                        units[name], generated_units[name], semaphore, args.retries
                    )
                    for name in generated_units
                )
            )
            audio_dir = I18N / "audio"
            for text_id, spoken_name in TARGETS.items():
                filename = f"{text_id}_{OUTPUT_SUFFIX}.mp3"
                shutil.copyfile(generated_units[spoken_name], audio_dir / filename)
                audios[text_id] = filename

        for text_id, spoken_name in TARGETS.items():
            texts[text_id] = spoken_name
            page = html_targets[text_id]
            page.write_text(
                replace_alt(page.read_text(encoding="utf-8"), text_id, spoken_name),
                encoding="utf-8",
            )
        texts_path.write_text(
            json.dumps(texts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        audios_path.write_text(
            json.dumps(audios, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    results = verify(
        json.loads(texts_path.read_text(encoding="utf-8")),
        json.loads(audios_path.read_text(encoding="utf-8")),
        html_targets,
    )
    report_path = ROOT / "reports" / "phonics-image-name-audit-v26.json"
    report_path.write_text(
        json.dumps(
            {
                "voice": VOICE,
                "selection": "Complete current set of concise phonics/name prompt images; ordinary scene and comprehension images remain descriptive.",
                "target_count": len(results),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Verified {len(results)} concise image-name recordings with {VOICE}.")


if __name__ == "__main__":
    asyncio.run(main())
