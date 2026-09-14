#!/usr/bin/env python3
"""Fail closed unless local and GitHub Actions produced identical outputs/facts."""
import argparse
import json
from pathlib import Path


def merge(local: dict, ci: dict) -> dict:
    for key in ("files", "facts"):
        if local.get(key) != ci.get(key):
            raise ValueError(f"local and CI {key} differ")
    return {
        "schema": "star-solar-star.merged-verification.v1",
        "status": "matching",
        "code_commit": ci["code_commit"],
        "lanes": [local["lane"], ci["lane"]],
        "files": local["files"],
        "facts": local["facts"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("local", type=Path)
    parser.add_argument("ci", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = merge(json.loads(args.local.read_text()), json.loads(args.ci.read_text()))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
