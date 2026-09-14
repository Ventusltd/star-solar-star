#!/usr/bin/env python3
"""Fail closed unless local and GitHub lanes report identical stable facts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from star_contract import canonical_bytes, write_json


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("result_schema") != "star-solar-star.lane-result.v1":
        raise ValueError(f"{path}: unsupported result schema")
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", type=Path, required=True)
    parser.add_argument("--ci", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    local, ci = load(args.local), load(args.ci)
    if local["lane"] == ci["lane"]:
        raise ValueError("independent results must have different lane names")
    if local["code_commit"] != ci["code_commit"]:
        raise ValueError("independent results used different code commits")
    if local["facts"] != ci["facts"]:
        raise ValueError("local and GitHub facts disagree; refusing promotion")
    evidence_sha = hashlib.sha256(canonical_bytes(local["facts"])).hexdigest()
    merged = {
        "result_schema": "star-solar-star.agreement.v1",
        "code_commit": local["code_commit"],
        "lanes": sorted([local["lane"], ci["lane"]]),
        "facts_sha256": evidence_sha,
        "facts": local["facts"],
    }
    write_json(args.output, merged)
    print(f"agreed facts sha256={evidence_sha}")
