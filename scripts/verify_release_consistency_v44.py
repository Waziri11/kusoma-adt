#!/usr/bin/env python3
"""Verify the v44 cross-device consistency release."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION = "44"


def main() -> None:
    html_files = sorted(ROOT.glob("*.html"))
    if len(html_files) != 104:
        raise RuntimeError(f"Expected 104 HTML files, found {len(html_files)}")

    required = (
        f'<script src="./assets/release-consistency.js?v={VERSION}"></script>',
        'http-equiv="Cache-Control"',
        'http-equiv="Pragma"',
        'http-equiv="Expires"',
        f'./assets/offline-preloader.js?v={VERSION}',
        f'./assets/image-description-default.js?v={VERSION}',
        f'./assets/base.bundle.local.js?v={VERSION}',
    )
    for page in html_files:
        source = page.read_text(encoding="utf-8")
        for item in required:
            if item not in source:
                raise RuntimeError(f"{page.name}: missing {item}")
        if source.count("release-consistency.js") != 1:
            raise RuntimeError(f"{page.name}: release bootstrap count is not one")
        if "?v=43" in source:
            raise RuntimeError(f"{page.name}: stale v43 query remains")

    config = json.loads((ROOT / "assets/config.json").read_text(encoding="utf-8"))
    release = json.loads((ROOT / "assets/release.json").read_text(encoding="utf-8"))
    if str(config.get("bundleVersion")) != VERSION:
        raise RuntimeError("config bundleVersion mismatch")
    if str(release.get("bundleVersion")) != VERSION:
        raise RuntimeError("release manifest version mismatch")

    bootstrap = ROOT / "assets/release-consistency.js"
    subprocess.run(["node", "--check", str(bootstrap)], check=True)
    source = bootstrap.read_text(encoding="utf-8")
    for behavior in (
        'cache: "no-store"',
        "caches.keys()",
        "requestUrl.pathname.startsWith(bookRootUrl.pathname)",
        "getRegistrations()",
        "scopeUrl.pathname.startsWith(bookRootUrl.pathname)",
        'searchParams.set("release", version)',
        'localStorage.setItem("adtBundleVersion", version)',
    ):
        if behavior not in source:
            raise RuntimeError(f"bootstrap is missing behavior: {behavior}")

    preloader = (ROOT / "assets/offline-preloader.js").read_text(encoding="utf-8")
    if f'"bundleVersion":"{VERSION}"' not in preloader:
        raise RuntimeError("offline preloader contains a stale config")

    print(
        "PASS: v44 manifest, 104 cache-safe HTML pages, offline data, "
        "legacy cache cleanup, and offline fallback are synchronized"
    )


if __name__ == "__main__":
    main()
