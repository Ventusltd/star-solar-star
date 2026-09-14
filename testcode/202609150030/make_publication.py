#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
entries = []
for path in sorted(ROOT.iterdir(), key=lambda item: item.name):
    if path.is_file() and path.name != "publication.json" and path.name != "__pycache__":
        raw = path.read_bytes().replace(b"\r\n", b"\n")
        entries.append({"path": path.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
with (ROOT / "publication.json").open("w", encoding="utf-8", newline="\n") as handle:
    handle.write(json.dumps({"schema": "globalgrid2050.testcode-publication.v1", "files": entries}, indent=2, sort_keys=True) + "\n")
