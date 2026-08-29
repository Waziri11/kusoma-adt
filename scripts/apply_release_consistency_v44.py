#!/usr/bin/env python3
"""Install the device-consistency bootstrap and bump the ADT bundle to v44."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION = "44"
PREVIOUS_VERSION = "43"
RELEASE_SCRIPT = f'<script src="./assets/release-consistency.js?v={VERSION}"></script>'
NO_CACHE_META = """    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">"""


def update_html(path: Path, *, verify: bool) -> None:
    source = path.read_text(encoding="utf-8")
    updated = source.replace(f"?v={PREVIOUS_VERSION}", f"?v={VERSION}")

    if 'http-equiv="Cache-Control"' not in updated:
        marker = "</head>"
        if marker not in updated:
            raise RuntimeError(f"{path.name}: missing </head>")
        updated = updated.replace(marker, f"{NO_CACHE_META}\n{marker}", 1)

    if "release-consistency.js" not in updated:
        marker = "</head>"
        updated = updated.replace(marker, f"    {RELEASE_SCRIPT}\n{marker}", 1)
    else:
        import re
        updated = re.sub(
            r'<script src="\./assets/release-consistency\.js\?v=\d+"></script>',
            RELEASE_SCRIPT,
            updated,
            count=1,
        )

    required = (
        RELEASE_SCRIPT,
        'http-equiv="Cache-Control"',
        'http-equiv="Pragma"',
        'http-equiv="Expires"',
        f'./assets/offline-preloader.js?v={VERSION}',
        f'./assets/image-description-default.js?v={VERSION}',
        f'./assets/base.bundle.local.js?v={VERSION}',
    )
    for item in required:
        if item not in updated:
            raise RuntimeError(f"{path.name}: missing {item}")
    if updated.count("release-consistency.js") != 1:
        raise RuntimeError(f"{path.name}: expected one consistency bootstrap")

    if verify:
        if source != updated:
            raise RuntimeError(f"{path.name}: release consistency changes not applied")
        return
    path.write_text(updated, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    config_path = ROOT / "assets" / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if str(config.get("bundleVersion")) not in {PREVIOUS_VERSION, VERSION}:
        raise RuntimeError(f"Unexpected bundleVersion: {config.get('bundleVersion')}")

    release_path = ROOT / "assets" / "release.json"
    release = json.loads(release_path.read_text(encoding="utf-8"))
    if str(release.get("bundleVersion")) != VERSION:
        raise RuntimeError("assets/release.json does not declare bundleVersion 44")

    html_files = sorted(ROOT.glob("*.html"))
    if len(html_files) != 104:
        raise RuntimeError(f"Expected 104 root HTML files, found {len(html_files)}")
    for page in html_files:
        update_html(page, verify=args.verify)

    if args.verify:
        if str(config.get("bundleVersion")) != VERSION:
            raise RuntimeError("assets/config.json is not bundleVersion 44")
        print("PASS: 104 HTML pages use the v44 release-consistency bootstrap")
        return

    config["bundleVersion"] = VERSION
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Applied device-consistency bootstrap to 104 pages; bundleVersion 44")


if __name__ == "__main__":
    main()
