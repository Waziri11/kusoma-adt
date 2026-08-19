"""Remove repeated HTML data-id attributes while preserving their inline fallback text."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
pages = json.loads((ROOT / "content/pages.json").read_text())
seen: set[str] = set()

for page in pages:
    path = ROOT / page["href"]
    source = path.read_text()

    def keep_first(match: re.Match[str]) -> str:
        text_id = match.group(1)
        if text_id in seen:
            return ""
        seen.add(text_id)
        return match.group(0)

    updated = re.sub(r'\s+data-id="([^"]+)"', keep_first, source)
    if updated != source:
        path.write_text(updated)
        print(path.name)
