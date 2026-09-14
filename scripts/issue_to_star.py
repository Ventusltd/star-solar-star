#!/usr/bin/env python3
"""Extract an approved star definition from an issue and write its stable path."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from star_contract import validate, write_json


def extract(body: str) -> dict:
    match = re.search(r"###\s+Star JSON\s*\n+```(?:json)?\s*\n([\s\S]*?)\n```", body, flags=re.IGNORECASE)
    if not match:
        raise ValueError("issue body lacks a fenced JSON object under '### Star JSON'")
    parsed = json.loads(match.group(1))
    validate(parsed)
    return parsed


def publish(star: dict, output_dir: Path) -> Path:
    path = output_dir / f"{star['id']}.star.json"
    if path.exists():
        current = json.loads(path.read_text(encoding="utf-8"))
        if current != star:
            raise FileExistsError(f"{path} already exists with different content; use a new id")
        return path
    write_json(path, star)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--body-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(publish(extract(args.body_file.read_text(encoding="utf-8")), args.output_dir).as_posix())


