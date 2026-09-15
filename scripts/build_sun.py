#!/usr/bin/env python3
"""Build the Sun Star's committed public-data payloads.

The builder is deliberately standard-library only. Network responses and pinned
GlobalGrid2050 files are hashed before any derived number is emitted.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import importlib.util
import json
import math
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any


USER_AGENT = "GlobalGrid2050-Sun-Star/1.0 (+https://github.com/Ventusltd/star-solar-star)"
PVLIVE = "https://api.pvlive.uk/pvlive/api/v4/gsp/0"
PV_TIMESTAMP_CONVENTION = "UTC interval end; day covers 00:30 through next 00:00"
PUBLIC_ROOT = "https://globalgrid2050.com"
GLOBALGRID_GITHUB = "https://raw.githubusercontent.com/Ventusltd/globalgrid2050/{commit}/{path}"
FEEDS = (
    {
        "name": "Solar Power Portal",
        "feed": "https://www.solarpowerportal.co.uk/rss.xml?content_types=article",
        "robots": "https://www.solarpowerportal.co.uk/robots.txt",
    },
    {
        "name": "pv magazine International",
        "feed": "https://www.pv-magazine.com/feed/",
        "robots": "https://www.pv-magazine.com/robots.txt",
    },
)
PINNED_PATHS = {
    "geometry": "scripts/gridbot_london_solar_daylight_geometry.py",
    "podcast": "podcast_transcripts/index.md",
    "pipeline": "pipelinenews_intelligence/202609050309/data/202608270055-8ab1807551bc-v8-fast-projects.json",
    "deployment": "solar_deployment_statistics/index.md",
    "components": "solar_components/index.md",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


class SourceLedger:
    def __init__(self, fetched_utc: str):
        self.fetched_utc = fetched_utc
        self.sources: list[dict[str, Any]] = []

    def add(self, *, name: str, url: str, data: bytes, kind: str, **extra: Any) -> None:
        row = {
            "name": name,
            "kind": kind,
            "url": url,
            "bytes": len(data),
            "sha256": sha256(data),
            "fetched_utc": self.fetched_utc,
        }
        row.update(extra)
        self.sources.append(row)


def fetch_bytes(url: str, timeout: int = 45) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"GET {url} returned HTTP {response.status}")
        return response.read()


def fetch_json(url: str, ledger: SourceLedger, name: str) -> dict[str, Any]:
    raw = fetch_bytes(url)
    ledger.add(name=name, url=url, data=raw, kind="api-json")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"{name} did not return a JSON object")
    return parsed


def read_pinned(root: Path, commit: str, key: str, ledger: SourceLedger) -> tuple[bytes, Path]:
    relative = PINNED_PATHS[key]
    path = root / relative
    raw = path.read_bytes()
    ledger.add(
        name=f"GlobalGrid2050 {key}",
        url=GLOBALGRID_GITHUB.format(commit=commit, path=relative),
        data=raw,
        kind="pinned-public-repository-file",
        repository="Ventusltd/globalgrid2050",
        commit=commit,
        path=relative,
    )
    return raw, path


def require_checkout_commit(root: Path, expected: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    actual = result.stdout.strip()
    if actual != expected:
        raise ValueError(f"GlobalGrid2050 checkout is {actual}, expected pinned commit {expected}")


def pv_url(as_of: dt.date, history_days: int) -> str:
    start = as_of - dt.timedelta(days=history_days - 1)
    query = urllib.parse.urlencode(
        {
            "start": f"{start.isoformat()}T00:30:00Z",
            "end": f"{(as_of + dt.timedelta(days=1)).isoformat()}T00:00:00Z",
            "extra_fields": "installedcapacity_mwp,capacity_mwp",
        }
    )
    return f"{PVLIVE}?{query}"


def interval_end(timestamp: Any) -> dt.datetime:
    if not isinstance(timestamp, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:(?:00|30):00Z", timestamp):
        raise ValueError("PV Live timestamp must be a UTC half-hour interval end")
    return dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def finite_power(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("PV Live power/capacity must be finite and nonnegative")
    return float(value)


def summarize_pv_day(date_text: str, day_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Recompute summaries only from a complete UTC day of end-stamped samples."""
    start = dt.datetime.combine(dt.date.fromisoformat(date_text), dt.time(), dt.timezone.utc)
    expected = [(start + dt.timedelta(minutes=30 * n)).strftime("%Y-%m-%dT%H:%M:%SZ") for n in range(1, 49)]
    if [row["timestamp_utc"] for row in day_rows] != expected:
        raise ValueError("PV Live day must contain 48 unique ordered half-hour interval ends with full UTC coverage")
    for row in day_rows:
        finite_power(row["generation_mw"])
        if row["installed_capacity_mwp"] is not None:
            finite_power(row["installed_capacity_mwp"])
    series = [[row["timestamp_utc"], float(row["generation_mw"])] for row in day_rows]
    peak = max(day_rows, key=lambda row: row["generation_mw"])
    return {
        "date": date_text, "timestamp_convention": PV_TIMESTAMP_CONVENTION,
        "interval_minutes": 30, "intervals": 48, "complete": True,
        "energy_mwh": round(math.fsum(row["generation_mw"] for row in day_rows) * 0.5, 3),
        "peak_mw": peak["generation_mw"], "peak_at_utc": peak["timestamp_utc"],
        "installed_capacity_mwp": next((row["installed_capacity_mwp"] for row in day_rows if row["installed_capacity_mwp"] is not None), None),
        "seed_sha256": sha256(canonical_json(series)), "series": day_rows,
    }


def parse_pvlive(payload: dict[str, Any], as_of: dt.date) -> tuple[dict[str, Any], dict[str, Any]]:
    columns = payload.get("meta")
    data = payload.get("data")
    if not isinstance(columns, list) or not isinstance(data, list):
        raise ValueError("PV Live response lacks meta/data arrays")
    if len(columns) != len(set(columns)):
        raise ValueError("PV Live response has duplicate columns")
    required = ("gsp_id", "datetime_gmt", "generation_mw")
    if any(name not in columns for name in required):
        raise ValueError(f"PV Live response lacks required columns: {required}")
    indexes = {name: columns.index(name) for name in columns}
    rows: list[dict[str, Any]] = []
    seen = set()
    for source_row in data:
        if not isinstance(source_row, list) or len(source_row) != len(columns):
            raise ValueError("PV Live row does not match metadata columns")
        if type(source_row[indexes["gsp_id"]]) is not int or source_row[indexes["gsp_id"]] != 0:
            raise ValueError("PV Live response contains a non-national GSP")
        timestamp = source_row[indexes["datetime_gmt"]]
        end = interval_end(timestamp)
        if timestamp in seen:
            raise ValueError("PV Live response contains duplicate timestamps")
        seen.add(timestamp)
        if (end - dt.timedelta(minutes=30)).date() > as_of:
            raise ValueError("PV Live response contains a day after the requested date")
        generation = finite_power(source_row[indexes["generation_mw"]])
        installed = None
        if "installedcapacity_mwp" in indexes and source_row[indexes["installedcapacity_mwp"]] is not None:
            installed = finite_power(source_row[indexes["installedcapacity_mwp"]])
        rows.append({"timestamp_utc": timestamp, "generation_mw": generation, "installed_capacity_mwp": installed})
    rows.sort(key=lambda row: row["timestamp_utc"])
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        date_text = (interval_end(row["timestamp_utc"]) - dt.timedelta(minutes=30)).date().isoformat()
        grouped[date_text].append(row)

    days: list[dict[str, Any]] = []
    for date_text in sorted(grouped):
        days.append(summarize_pv_day(date_text, grouped[date_text]))
    if not days:
        raise ValueError("PV Live response contains no rows")
    first_date = dt.date.fromisoformat(days[0]["date"])
    if [day["date"] for day in days] != [(first_date + dt.timedelta(days=n)).isoformat() for n in range(len(days))]:
        raise ValueError("PV Live response has missing UTC days")
    requested = as_of.isoformat()
    selected = next((row for row in days if row["date"] == requested), days[-1])
    today = {
        "requested_date": requested,
        "data_date": selected["date"],
        "used_latest_available": selected["date"] != requested,
        **selected,
    }
    history = {
        "schema": "star-solar-star.history.v2",
        "energy_formula": "sum of half-hourly generation_mw multiplied by 0.5 hours",
        "days": days,
    }
    return today, history


def load_geometry(root: Path, as_of: dt.date) -> dict[str, Any]:
    path = root / PINNED_PATHS["geometry"]
    spec = importlib.util.spec_from_file_location("globalgrid_solar_geometry", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import geometry module at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    result = module.solar_geometry_for_day(as_of)
    if not isinstance(result, dict):
        raise ValueError("solar_geometry_for_day did not return an object")
    result["implementation"] = PINNED_PATHS["geometry"]
    return result


def decode_dictionary(dictionaries: dict[str, Any], field: str, value: Any) -> Any:
    options = dictionaries.get(field)
    if isinstance(value, int) and isinstance(options, list) and 0 <= value < len(options):
        return options[value]
    return value


def build_uk_solar(raw: bytes, release: str = "202609050309") -> dict[str, Any]:
    source = json.loads(raw)
    fields = source["fields"]
    dictionaries = source.get("dictionaries", {})
    index = {name: fields.index(name) for name in fields}
    projects: list[dict[str, Any]] = []
    for row in source["rows"]:
        technology = decode_dictionary(dictionaries, "technology", row[index["technology"]])
        if not str(technology).lower().startswith("solar"):
            continue
        repd_ref = str(row[index["repd_ref"]])
        capacity_value = row[index["capacity_mw"]]
        latitude_value = row[index["latitude"]]
        longitude_value = row[index["longitude"]]
        projects.append(
            {
                "repd_ref": repd_ref,
                "gg_project_id": row[index["gg_project_id"]],
                "name": row[index["name"]],
                "technology": technology,
                "status": decode_dictionary(dictionaries, "status", row[index["status"]]),
                "capacity_mw": None if capacity_value in (None, "") else float(capacity_value),
                "county": decode_dictionary(dictionaries, "county", row[index["county"]]),
                "region": decode_dictionary(dictionaries, "region", row[index["region"]]),
                "operator": decode_dictionary(dictionaries, "operator", row[index["operator"]]),
                "geometry_status": decode_dictionary(dictionaries, "geometry_status", row[index["geometry_status"]]),
                "latitude": None if latitude_value in (None, "") else float(latitude_value),
                "longitude": None if longitude_value in (None, "") else float(longitude_value),
                "deep_link": f"{PUBLIC_ROOT}/pipelinenews_intelligence/{release}/?repd_ref={urllib.parse.quote(repd_ref)}",
            }
        )
    projects.sort(key=lambda project: project["repd_ref"])
    status_counts: dict[str, int] = defaultdict(int)
    for project in projects:
        status_counts[str(project["status"])] += 1
    missing = [project["repd_ref"] for project in projects if project["latitude"] is None or project["longitude"] is None]
    return {
        "schema": "star-solar-star.uk-projects.v1",
        "source_release": release,
        "source_generation": source.get("generation"),
        "source_sha256": sha256(raw),
        "solar_projects": len(projects),
        "solar_capacity_mw": round(sum(project["capacity_mw"] or 0 for project in projects), 3),
        "with_coordinates": len(projects) - len(missing),
        "without_coordinates": len(missing),
        "missing_coordinate_repd_refs": missing,
        "by_status": dict(sorted(status_counts.items())),
        "projects": projects,
    }


def build_voices(markdown: str) -> dict[str, Any]:
    matches = re.findall(r'<li><a href="#([^"]+)">([\s\S]*?)</a></li>', markdown, flags=re.IGNORECASE)
    episodes: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor, title_markup in matches:
        if anchor in seen:
            continue
        seen.add(anchor)
        title = html.unescape(re.sub(r"<[^>]+>", "", title_markup))
        title = re.sub(r"\s+", " ", title).strip()
        episodes.append(
            {
                "title": title,
                "link": f"{PUBLIC_ROOT}/podcast_transcripts/#{anchor}",
                "attribution": "The Future of Solar Photovoltaics podcast",
            }
        )
    if not episodes:
        raise ValueError("podcast index contains no episode links")
    return {"schema": "star-solar-star.voices.v1", "episodes": episodes}


def parse_markdown_scan(markdown: str) -> dict[str, Any]:
    lines = markdown.splitlines()
    headings = []
    tables = []
    for number, line in enumerate(lines, start=1):
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            headings.append({"level": len(heading.group(1)), "text": heading.group(2), "source_line": number})
    index = 0
    while index + 1 < len(lines):
        if "|" not in lines[index] or not re.match(r"^\s*\|?\s*:?-+", lines[index + 1]):
            index += 1
            continue
        header = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
        rows = []
        cursor = index + 2
        while cursor < len(lines) and "|" in lines[cursor] and lines[cursor].strip():
            cells = [cell.strip() for cell in lines[cursor].strip().strip("|").split("|")]
            rows.append({header[pos] if pos < len(header) else f"column_{pos + 1}": value for pos, value in enumerate(cells)})
            cursor += 1
        tables.append({"source_line": index + 1, "columns": header, "rows": rows})
        index = cursor
    return {"headings": headings, "tables": tables}


def robots_allows(robots_raw: bytes, robots_url: str, target_url: str) -> bool:
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(robots_raw.decode("utf-8", errors="replace").splitlines())
    return parser.can_fetch(USER_AGENT, target_url)


def child_text(item: ET.Element, name: str) -> str:
    node = item.find(name)
    return "" if node is None or node.text is None else node.text.strip()


def parse_feed(raw: bytes, source_name: str, feed_url: str, limit: int = 20) -> list[dict[str, str]]:
    root = ET.fromstring(raw)
    items = root.findall("./channel/item")
    if not items:
        items = root.findall("{http://www.w3.org/2005/Atom}entry")
    entries: list[dict[str, str]] = []
    for item in items[:limit]:
        title = child_text(item, "title") or child_text(item, "{http://www.w3.org/2005/Atom}title")
        link = child_text(item, "link")
        if not link:
            link_node = item.find("{http://www.w3.org/2005/Atom}link")
            link = "" if link_node is None else link_node.attrib.get("href", "")
        published = (
            child_text(item, "pubDate")
            or child_text(item, "{http://purl.org/dc/elements/1.1/}date")
            or child_text(item, "{http://www.w3.org/2005/Atom}published")
            or child_text(item, "{http://www.w3.org/2005/Atom}updated")
        )
        if title and link:
            entries.append({"title": html.unescape(title), "link": link, "published": published, "attribution": source_name})
    if not entries:
        raise ValueError(f"{source_name} feed contains no readable entries")
    return entries


def build_press(ledger: SourceLedger) -> dict[str, Any]:
    sources = []
    all_entries = []
    for config in FEEDS:
        robots_raw = fetch_bytes(config["robots"])
        ledger.add(name=f"{config['name']} robots.txt", url=config["robots"], data=robots_raw, kind="robots.txt")
        allowed = robots_allows(robots_raw, config["robots"], config["feed"])
        if not allowed:
            raise PermissionError(f"robots.txt does not allow {USER_AGENT} to fetch {config['feed']}")
        feed_raw = fetch_bytes(config["feed"])
        ledger.add(
            name=f"{config['name']} public RSS feed",
            url=config["feed"],
            data=feed_raw,
            kind="rss",
            robots_url=config["robots"],
            robots_allowed=True,
            fields_retained=["title", "link", "published", "attribution"],
        )
        entries = parse_feed(feed_raw, config["name"], config["feed"])
        sources.append({"name": config["name"], "feed": config["feed"], "entries": len(entries)})
        all_entries.extend(entries)
    return {"schema": "star-solar-star.press.v1", "policy": "RSS metadata only: title, link, date, attribution", "sources": sources, "entries": all_entries}


def build(args: argparse.Namespace) -> dict[str, Path]:
    root = args.globalgrid_root.resolve()
    output = args.output.resolve()
    require_checkout_commit(root, args.globalgrid_commit)
    as_of = dt.date.fromisoformat(args.as_of)
    built_utc = args.built_utc or utc_now()
    ledger = SourceLedger(built_utc)

    pv_payload = fetch_json(pv_url(as_of, args.history_days), ledger, "Sheffield Solar PV Live national GSP 0")
    today_series, history = parse_pvlive(pv_payload, as_of)

    geometry_raw, _ = read_pinned(root, args.globalgrid_commit, "geometry", ledger)
    del geometry_raw
    geometry = load_geometry(root, as_of)
    podcast_raw, _ = read_pinned(root, args.globalgrid_commit, "podcast", ledger)
    pipeline_raw, _ = read_pinned(root, args.globalgrid_commit, "pipeline", ledger)
    deployment_raw, _ = read_pinned(root, args.globalgrid_commit, "deployment", ledger)
    components_raw, _ = read_pinned(root, args.globalgrid_commit, "components", ledger)
    press = build_press(ledger)

    today = {
        "schema": "star-solar-star.today.v2",
        "built_utc": built_utc,
        "seed": today_series["seed_sha256"],
        "seed_rule": "sha256 of canonical JSON for the selected day's ordered [timestamp_utc, generation_mw] PV Live series",
        "pv_live": today_series,
        "london_solar_geometry": geometry,
    }
    voices = build_voices(podcast_raw.decode("utf-8"))
    uk_solar = build_uk_solar(pipeline_raw)
    provenance = {
        "schema": "star-solar-star.provenance.v1",
        "built_utc": built_utc,
        "globalgrid_commit": args.globalgrid_commit,
        "sources": ledger.sources,
        "scans": {
            "solar_deployment_statistics": parse_markdown_scan(deployment_raw.decode("utf-8")),
            "solar_components": parse_markdown_scan(components_raw.decode("utf-8")),
        },
    }
    values = {
        "today.json": today,
        "history.json": history,
        "uk-solar.json": uk_solar,
        "voices.json": voices,
        "press.json": press,
        "provenance.json": provenance,
    }
    written = {}
    for name, value in values.items():
        path = output / name
        write_json(path, value)
        written[name] = path
    return written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--globalgrid-root", type=Path, required=True)
    parser.add_argument("--globalgrid-commit", required=True)
    parser.add_argument("--output", type=Path, default=Path("sun"))
    latest_complete_day = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)
    parser.add_argument("--as-of", default=latest_complete_day.isoformat())
    parser.add_argument("--history-days", type=int, default=30)
    parser.add_argument("--built-utc", help="Explicit timestamp for reproducible verification builds")
    args = parser.parse_args(argv)
    if args.history_days < 1 or args.history_days > 366:
        parser.error("--history-days must be between 1 and 366")
    if not re.fullmatch(r"[0-9a-f]{40}", args.globalgrid_commit):
        parser.error("--globalgrid-commit must be a full 40-character lowercase Git SHA")
    return args


if __name__ == "__main__":
    files = build(parse_args())
    for name, path in files.items():
        print(f"{name}: {path.stat().st_size} bytes sha256={sha256(path.read_bytes())}")
