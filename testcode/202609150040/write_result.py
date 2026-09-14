#!/usr/bin/env python3
"""Write the stable evidence used to compare independent execution lanes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from star_contract import validate, write_json


def result_for(star: dict, lane: str, code_commit: str) -> dict:
    summary = validate(star)
    sources = {row["id"]: row for row in star["sources"]}
    return {
        "result_schema": "star-solar-star.lane-result.v1",
        "lane": lane,
        "code_commit": code_commit,
        "facts": {
            "id": summary["id"],
            "type": summary["type"],
            "region": star["region"],
            "observations": star["observations"],
            "observation_count": summary["observations"],
            "seed": summary["seed"],
            "source_urls": {key: sources[key]["url"] for key in sorted(sources)},
            "irena_pdf_sha256": sources["irena-rsc-2026"]["sha256"],
            "globalgrid_commit": sources["globalgrid-solar-deployment"]["commit"],
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--star", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lane", required=True)
    parser.add_argument("--code-commit", required=True)
    args = parser.parse_args()
    star = json.loads(args.star.read_text(encoding="utf-8"))
    value = result_for(star, args.lane, args.code_commit)
    write_json(args.output, value)
    print(json.dumps(value["facts"], ensure_ascii=False, sort_keys=True))
