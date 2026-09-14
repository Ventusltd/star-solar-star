#!/usr/bin/env python3
"""Create a deterministic manifest for the candidate implementation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from star_contract import write_json


ROOT = Path(__file__).resolve().parent
FILES = [
    "README.md",
    "build_global_star.py",
    "create/index.html",
    "global-solar.star.json",
    "iea-audited-statements.json",
    "issue_to_star.py",
    "merge_results.py",
    "star.schema.json",
    "star_contract.py",
    "test_country_star.py",
    "write_result.py",
]


if __name__ == "__main__":
    rows = []
    for relative in FILES:
        raw = (ROOT / relative).read_bytes()
        rows.append({"path": relative, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    write_json(ROOT / "publication.json", {"schema": "star-solar-star.candidate-publication.v1", "files": rows})
    print(json.dumps({row["path"]: row["sha256"] for row in rows}, sort_keys=True))
