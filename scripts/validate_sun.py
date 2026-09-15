#!/usr/bin/env python3
"""Fail-closed validation for the six committed Sun Star payloads."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path

from build_sun import summarize_pv_day


NAMES = {"today.json", "history.json", "uk-solar.json", "voices.json", "press.json", "provenance.json"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def load(root: Path, name: str):
    path = root / name
    if not path.is_file():
        raise ValueError(f"missing {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate(root: Path) -> dict:
    present = {path.name for path in root.glob("*.json")}
    if present != NAMES:
        raise ValueError(f"expected exactly {sorted(NAMES)}, found {sorted(present)}")
    today = load(root, "today.json")
    history = load(root, "history.json")
    uk = load(root, "uk-solar.json")
    voices = load(root, "voices.json")
    press = load(root, "press.json")
    provenance = load(root, "provenance.json")

    if today.get("schema") != "star-solar-star.today.v2":
        raise ValueError("unexpected today schema")
    if history.get("schema") != "star-solar-star.history.v2":
        raise ValueError("unexpected history schema")
    if not SHA256.fullmatch(str(today.get("seed", ""))):
        raise ValueError("today seed is not a full SHA-256")
    if today["seed"] != today["pv_live"].get("seed_sha256"):
        raise ValueError("top-level and PV Live seeds differ")
    if not history.get("days"):
        raise ValueError("history is empty")
    dates = [dt.date.fromisoformat(day["date"]) for day in history["days"]]
    if dates != [dates[0] + dt.timedelta(days=n) for n in range(len(dates))]:
        raise ValueError("history dates must be unique, ordered and consecutive")
    for day in history["days"]:
        if day.get("complete") is not True:
            raise ValueError("PV Live day must be explicitly complete")
        expected = summarize_pv_day(day["date"], day["series"])
        if day != expected:
            raise ValueError("history PV Live summaries do not match recomputed series")
    selected = today["pv_live"]
    requested = dt.date.fromisoformat(selected["requested_date"])
    data_date = dt.date.fromisoformat(selected["data_date"])
    if data_date > requested or selected.get("date") != selected["data_date"]:
        raise ValueError("selected/source/requested PV Live dates disagree")
    if selected.get("used_latest_available") is not (data_date != requested):
        raise ValueError("PV Live fallback flag disagrees with requested/source dates")
    if today["london_solar_geometry"].get("date") != requested.isoformat():
        raise ValueError("geometry must identify the requested date")
    if history["days"][-1]["date"] != selected["data_date"]:
        raise ValueError("history does not end on the selected day")
    expected_selected = {**history["days"][-1], "requested_date": requested.isoformat(),
                         "data_date": data_date.isoformat(), "used_latest_available": data_date != requested}
    if selected != expected_selected:
        raise ValueError("selected PV Live day does not match verified history")

    projects = uk.get("projects", [])
    missing = [p["repd_ref"] for p in projects if p.get("latitude") is None or p.get("longitude") is None]
    if uk.get("solar_projects") != len(projects):
        raise ValueError("solar project count disagrees with project rows")
    if uk.get("with_coordinates") + uk.get("without_coordinates") != len(projects):
        raise ValueError("coordinate counts do not sum to project count")
    if uk.get("missing_coordinate_repd_refs") != missing:
        raise ValueError("missing coordinate list disagrees with project rows")
    if len({p["repd_ref"] for p in projects}) != len(projects):
        raise ValueError("repd_ref is not unique")

    if not voices.get("episodes"):
        raise ValueError("voices has no episodes")
    allowed_press = {"title", "link", "published", "attribution"}
    if not press.get("entries"):
        raise ValueError("press has no entries")
    for entry in press["entries"]:
        if set(entry) != allowed_press:
            raise ValueError(f"press entry includes fields outside RSS metadata policy: {set(entry)}")

    sources = provenance.get("sources", [])
    if not sources:
        raise ValueError("provenance has no sources")
    for source in sources:
        if not source.get("url") or not source.get("fetched_utc"):
            raise ValueError("provenance source lacks URL or fetched time")
        if not isinstance(source.get("bytes"), int) or source["bytes"] < 1:
            raise ValueError("provenance source lacks positive byte count")
        if not SHA256.fullmatch(str(source.get("sha256", ""))):
            raise ValueError("provenance source lacks SHA-256")
    if set(provenance.get("scans", {})) != {"solar_components", "solar_deployment_statistics"}:
        raise ValueError("the two required estate scans are not present")
    return {
        "date": today["pv_live"]["data_date"],
        "seed": today["seed"],
        "solar_projects": len(projects),
        "with_coordinates": uk["with_coordinates"],
        "press_entries": len(press["entries"]),
        "provenance_sources": len(sources),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, nargs="?", default=Path("sun"))
    result = validate(parser.parse_args().root)
    print(json.dumps(result, sort_keys=True))
