#!/usr/bin/env python3
"""Write a compact, comparable result from a candidate build directory."""
import argparse
import hashlib
import json
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--sun", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--lane", required=True)
parser.add_argument("--code-commit", required=True)
args = parser.parse_args()


def load(name):
    return json.loads((args.sun / name).read_text(encoding="utf-8"))


files = {}
for path in sorted(args.sun.glob("*.json")):
    raw = path.read_bytes()
    files[path.name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
today = load("today.json")
uk = load("uk-solar.json")
press = load("press.json")
provenance = load("provenance.json")
result = {
    "schema": "star-solar-star.candidate-result.v1",
    "lane": args.lane,
    "code_commit": args.code_commit,
    "files": files,
    "facts": {
        "data_date": today["pv_live"]["data_date"],
        "pv_intervals": today["pv_live"]["intervals"],
        "pv_complete": today["pv_live"]["complete"],
        "seed_sha256": today["seed"],
        "solar_projects": uk["solar_projects"],
        "solar_capacity_mw": uk["solar_capacity_mw"],
        "with_coordinates": uk["with_coordinates"],
        "without_coordinates": uk["without_coordinates"],
        "missing_coordinate_repd_refs": uk["missing_coordinate_repd_refs"],
        "press_entries": len(press["entries"]),
        "provenance_sources": len(provenance["sources"]),
    },
}
args.output.parent.mkdir(parents=True, exist_ok=True)
with args.output.open("w", encoding="utf-8", newline="\n") as handle:
    handle.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
