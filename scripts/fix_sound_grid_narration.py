#!/usr/bin/env python3
"""Replace letter-grid image descriptions with sounds-only narration.

The target list is intentionally explicit and follows the visible row-major
order of each image.  It includes every current image in the book whose main
content is a single grapheme or a grid of graphemes; ordinary object images and
screenshots containing prose are not targets.
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
from typing import Dict, List, Sequence, Tuple

from fix_all_letter_sound_audio import (
    READINGS,
    VOICE,
    probe_audio,
    run_ffmpeg,
    synthesize_unit,
    to_wav,
    unit_filename,
)


ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "content" / "i18n" / "sw-TZ"
OUTPUT_SUFFIX = "sounds_only_v26"
PAUSE_SECONDS = 0.45
Segment = Tuple[str, str]

# Tokens are the actual displayed sounds in visual row-major order. Repeated
# tokens are retained. The reversed "hc" distractors on pg066 are deliberately
# split into their two displayed sounds, h then c.
TARGETS: Dict[str, List[str]] = {
    "pg018_im003_crop1_crop1": ["a", "b", "o", "d", "b", "p", "i", "b"],
    "pg031_im003_crop1_crop1": ["l"],
    "pg042_im003": ["g"],
    "pg042_im006": ["g", "d", "d", "g", "p", "b", "g", "p"],
    "pg046_im002_crop_v1": ["y"],
    "pg046_im003": ["u", "y", "j", "g", "y", "g", "y", "p"],
    "pg049_im003_crop_v1_crop1": ["z"],
    "pg049_im004": ["z", "m", "k", "z", "b", "z", "p", "u"],
    "pg056_im003": ["r"],
    "pg056_im005_crop_v1": ["r", "h", "e", "r", "l", "r", "i", "k"],
    "pg059_im008_crop_v1": ["u", "w", "m", "w", "a", "m", "n"],
    "pg062_im010_crop1": ["v", "w", "n", "v", "u", "v", "w", "u"],
    "pg066_im004": ["ch", "m", "h", "c", "ch", "h", "c", "ch", "n", "u"],
    "pg068_im004": ["ch", "ng", "sh", "ch", "sh", "ch", "ng", "sh"],
    "pg070_im003_crop1": ["kw", "th", "mb", "nd", "th", "kw", "ng", "th"],
    "pg072_im004": ["sh", "ng", "mb", "nd", "mb", "nd", "sh", "mb"],
    "pg078_im004": ["nd", "ng", "ny", "sh", "mb", "ng", "sh", "ng"],
    "pg080_im007": ["nd", "ny", "ng", "nd", "ng", "nd", "ny", "mb"],
    "pg083_im003_crop1": ["nd", "kw", "mb", "nd", "kw", "mb", "nd", "ng"],
    "pg098_im004": [
        "a", "y", "w", "v", "u", "t", "s", "r",
        "g", "h", "p", "m", "z", "b", "e", "f",
        "d", "a", "ch", "d", "n", "w", "m", "e",
        "n", "ch", "k", "u", "j", "b", "g", "n",
        "i", "l", "d", "b", "p", "d", "o", "v",
        "w", "r", "n", "l", "j", "y", "p", "y",
        "a", "ch", "h", "t", "u", "e", "o", "k",
        "h", "z", "h", "j", "m", "a", "g", "l",
        "i", "v", "t", "r", "s", "d", "k", "r",
        "b", "ch", "v", "p", "h", "r", "j", "ch",
        "f", "s", "a", "t", "y", "g", "v", "j",
        "w", "l", "o", "k", "g", "l", "s", "p",
        "o", "i", "t", "f", "h", "r", "l", "z",
        "b", "j", "ch", "f", "z", "d", "o", "j",
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--retries", type=int, default=6)
    return parser.parse_args()


def display_text(tokens: Sequence[str]) -> str:
    return ", ".join(tokens)


def sound_segments(tokens: Sequence[str]) -> List[Segment]:
    segments: List[Segment] = []
    for token in tokens:
        if token not in READINGS:
            raise RuntimeError(f"No phonics reading for {token!r}")
        segments.extend(("sound", reading) for reading in READINGS[token])
    return segments


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


def assemble(
    text_id: str,
    segments: Sequence[Segment],
    wav_files: Dict[Segment, Path],
    silence: Path,
    stage: Path,
) -> Path:
    output = stage / f"{text_id}_{OUTPUT_SUFFIX}.mp3"
    concat_file = stage / f"concat_{text_id}.txt"
    sequence: List[Path] = []
    for index, segment in enumerate(segments):
        sequence.append(wav_files[segment])
        if index < len(segments) - 1:
            sequence.append(silence)
    concat_file.write_text(
        "".join(f"file '{path}'\n" for path in sequence), encoding="utf-8"
    )
    run_ffmpeg(
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c:a", "libmp3lame", "-b:a", "128k", str(output),
    )
    return output


def signal_levels(path: Path) -> Dict[str, float]:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    output = result.stderr
    mean_match = re.search(r"mean_volume:\s*(-?[0-9.]+) dB", output)
    max_match = re.search(r"max_volume:\s*(-?[0-9.]+) dB", output)
    if not mean_match or not max_match:
        raise RuntimeError(f"Could not measure signal levels: {path}")
    levels = {
        "mean_volume_db": float(mean_match.group(1)),
        "max_volume_db": float(max_match.group(1)),
    }
    if levels["max_volume_db"] < -45:
        raise RuntimeError(f"Generated audio is effectively silent: {path}")
    return levels


def detected_pause_count(path: Path) -> int:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-i", str(path), "-af",
            "silencedetect=noise=-45dB:d=0.35", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )
    return len(re.findall(r"silence_end:", result.stderr))


def verify(
    texts: Dict[str, str], audios: Dict[str, str], html_targets: Dict[str, Path]
) -> List[Dict[str, object]]:
    results: List[Dict[str, object]] = []
    for text_id, tokens in TARGETS.items():
        expected = display_text(tokens)
        if texts.get(text_id) != expected:
            raise RuntimeError(f"Unexpected text for {text_id}: {texts.get(text_id)!r}")
        filename = audios.get(text_id)
        expected_filename = f"{text_id}_{OUTPUT_SUFFIX}.mp3"
        if filename != expected_filename:
            raise RuntimeError(f"Unexpected mapping for {text_id}: {filename!r}")
        page_source = html_targets[text_id].read_text(encoding="utf-8")
        image_match = re.search(
            rf"<img\b[^>]*\bdata-id=(?:\"{re.escape(text_id)}\"|'{re.escape(text_id)}')[^>]*>",
            page_source,
            re.IGNORECASE,
        )
        alt_match = re.search(r"\balt\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", image_match.group(0), re.I)
        actual_alt = html.unescape((alt_match.group(1) or alt_match.group(2)) if alt_match else "")
        if actual_alt != expected:
            raise RuntimeError(f"Unexpected HTML alt for {text_id}: {actual_alt!r}")
        audio_path = I18N / "audio" / expected_filename
        probe = probe_audio(audio_path)
        levels = signal_levels(audio_path)
        spoken_unit_count = len(sound_segments(tokens))
        pause_count = detected_pause_count(audio_path)
        minimum_pause_count = max(0, spoken_unit_count - 1)
        if pause_count < minimum_pause_count:
            raise RuntimeError(
                f"{text_id} has {pause_count} detectable pauses; "
                f"expected at least {minimum_pause_count}"
            )
        results.append(
            {
                "text_id": text_id,
                "page": html_targets[text_id].name,
                "displayed_sound_count": len(tokens),
                "spoken_unit_count": spoken_unit_count,
                "detected_pause_count": pause_count,
                "sounds": tokens,
                "audio_filename": expected_filename,
                **probe,
                **levels,
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
        target_segments = {
            text_id: sound_segments(tokens) for text_id, tokens in TARGETS.items()
        }
        units = sorted(
            {segment for segments in target_segments.values() for segment in segments},
            key=lambda item: item[1],
        )
        with tempfile.TemporaryDirectory(prefix="kusoma-sound-grids-") as name:
            stage = Path(name)
            raw_files = {unit: stage / unit_filename(unit, "mp3") for unit in units}
            semaphore = asyncio.Semaphore(args.concurrency)
            await asyncio.gather(
                *(
                    synthesize_unit(unit, raw_files[unit], semaphore, args.retries)
                    for unit in units
                )
            )
            wav_files: Dict[Segment, Path] = {}
            for unit in units:
                wav = stage / unit_filename(unit, "wav")
                to_wav(raw_files[unit], wav)
                wav_files[unit] = wav
            silence = stage / "pause.wav"
            run_ffmpeg(
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                "-t", str(PAUSE_SECONDS), "-c:a", "pcm_s16le", str(silence),
            )
            generated = {
                text_id: assemble(
                    text_id, segments, wav_files, silence, stage
                )
                for text_id, segments in target_segments.items()
            }
            audio_dir = I18N / "audio"
            for text_id, generated_file in generated.items():
                shutil.copyfile(generated_file, audio_dir / generated_file.name)
                audios[text_id] = generated_file.name

        for text_id, tokens in TARGETS.items():
            value = display_text(tokens)
            texts[text_id] = value
            page = html_targets[text_id]
            page.write_text(
                replace_alt(page.read_text(encoding="utf-8"), text_id, value),
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
    report_path = ROOT / "reports" / "sound-grid-narration-audit-v26.json"
    report_path.write_text(
        json.dumps(
            {
                "voice": VOICE,
                "pause_seconds": PAUSE_SECONDS,
                "selection": "Every current image whose main content is one grapheme or a grapheme grid; excludes ordinary object images and prose screenshots.",
                "target_count": len(results),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Verified {len(results)} sounds-only image recordings with {VOICE}; "
        f"fixed pauses are {PAUSE_SECONDS:.2f} seconds."
    )


if __name__ == "__main__":
    asyncio.run(main())
