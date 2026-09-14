#!/usr/bin/env python3
"""Build a global solar definition from dated IRENA/IEA public sources."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

from star_contract import CANONICALIZATION, seed_for, validate, write_json


USER_AGENT = "GlobalGrid2050-Star-Creator/1.0 (+https://github.com/Ventusltd/star-solar-star)"
IRENA_URL = "https://www.irena.org/-/media/Files/IRENA/Agency/Publication/2026/Mar/IRENA_DAT_RE_capacity_statistics_2026.pdf"
IEA_SOLAR_URL = "https://www.iea.org/reports/global-energy-review-2026/technology-solar-pv-and-wind"
IEA_TRENDS_URL = "https://www.iea.org/reports/global-energy-review-2026/global-trends"
GLOBALGRID_COMMIT = "35f07f9c0ef6bbdaae3c9f27f5a361118f49624f"
GLOBALGRID_URL = f"https://raw.githubusercontent.com/Ventusltd/globalgrid2050/{GLOBALGRID_COMMIT}/solar_deployment_statistics/index.md"
IRENA_SHA256 = "fc580bd4f4ee39ef20de6b1ce3926005a4e3e3b8e2c92fd6a16d175a52515921"
FIXTURE = Path(__file__).with_name("iea-audited-statements.json")


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f"GET {url} returned HTTP {response.status}")
        return response.read()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def visible_text(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def source(source_id: str, publisher: str, title: str, url: str, published: str, accessed: str, raw: bytes, **extra):
    row = {
        "id": source_id,
        "publisher": publisher,
        "title": title,
        "url": url,
        "published": published,
        "accessed_utc": accessed,
        "bytes": len(raw),
        "sha256": digest(raw),
    }
    row.update(extra)
    return row


def iea_payload(source_id: str, url: str, allow_audited_fixture_on_403: bool) -> tuple[bytes | None, str, dict | None]:
    try:
        raw = fetch(url)
        return raw, visible_text(raw), None
    except urllib.error.HTTPError as exc:
        if exc.code != 403 or not allow_audited_fixture_on_403:
            raise
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        evidence = next((row for row in fixture["sources"] if row["id"] == source_id), None)
        if evidence is None or evidence["url"] != url:
            raise ValueError(f"audited fixture does not bind {source_id} to {url}") from exc
        if not isinstance(evidence["bytes"], int) or evidence["bytes"] <= 0 or not re.fullmatch(r"[0-9a-f]{64}", evidence["sha256"]):
            raise ValueError(f"audited fixture provenance is invalid for {source_id}") from exc
        return None, " ".join(evidence["markers"]), evidence


def iea_source(source_id: str, title: str, url: str, accessed: str, raw: bytes | None, evidence: dict | None) -> dict:
    if raw is not None:
        return source(source_id, "International Energy Agency", title, url, "2026-04-20", accessed, raw, licence="CC BY 4.0")
    assert evidence is not None
    return {
        "id": source_id,
        "publisher": "International Energy Agency",
        "title": title,
        "url": url,
        "published": "2026-04-20",
        "accessed_utc": accessed,
        "bytes": evidence["bytes"],
        "sha256": evidence["sha256"],
        "licence": "CC BY 4.0",
        "retrieval": "audited local observation; GitHub runner received HTTP 403",
    }


def build(accessed_utc: str | None = None, allow_audited_fixture_on_403: bool = False) -> dict:
    accessed = accessed_utc or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    irena_raw = fetch(IRENA_URL)
    iea_solar_raw, solar_text, iea_solar_evidence = iea_payload("iea-ger-2026-solar", IEA_SOLAR_URL, allow_audited_fixture_on_403)
    iea_trends_raw, trends_text, iea_trends_evidence = iea_payload("iea-ger-2026-trends", IEA_TRENDS_URL, allow_audited_fixture_on_403)
    estate_raw = fetch(GLOBALGRID_URL)
    if digest(irena_raw) != IRENA_SHA256 or not irena_raw.startswith(b"%PDF"):
        raise ValueError("IRENA report bytes differ from the audited Renewable Capacity Statistics 2026 PDF")
    estate_text = estate_raw.decode("utf-8", errors="strict")
    required_solar = ("surpassing 600 GW", "cumulative solar PV capacity to around 2 800 GW")
    required_trends = ("record increase of 600 TWh", "nearly 2 700 TWh", "over 8%")
    if any(marker not in solar_text for marker in required_solar):
        raise ValueError("IEA solar page no longer contains the audited 2025 capacity statements")
    if any(marker not in trends_text for marker in required_trends):
        raise ValueError("IEA global trends page no longer contains the audited 2025 generation statements")
    if "# Global Solar PV Deployment 2025" not in estate_text:
        raise ValueError("pinned estate solar deployment page has an unexpected title")

    observations = [
        {
            "key": "irena:solar-pv-capacity:world:2025",
            "metric": "solar photovoltaic installed capacity",
            "period": "2025",
            "value": 2383162,
            "unit": "MW",
            "relation": "exact",
            "source_id": "irena-rsc-2026",
            "locator": "PDF page 36, Solar photovoltaic table, World row, 2025 column",
        },
        {
            "key": "irena:solar-pv-net-change:world:2025",
            "metric": "solar photovoltaic installed-capacity net change",
            "period": "2025",
            "value": 510349,
            "unit": "MW",
            "relation": "exact",
            "source_id": "irena-rsc-2026",
            "locator": "Derived from PDF page 36 World row: 2,383,162 MW (2025) minus 1,872,813 MW (2024)",
            "derivation": {"formula": "2025 capacity minus 2024 capacity", "inputs_mw": [2383162, 1872813]},
        },
        {
            "key": "iea:solar-pv-capacity:world:2025",
            "metric": "solar photovoltaic installed capacity",
            "period": "2025",
            "value": 2800,
            "unit": "GW",
            "relation": "approximately",
            "source_id": "iea-ger-2026-solar",
            "locator": "Technology: Solar PV and wind; 2025 capacity paragraph",
        },
        {
            "key": "iea:solar-pv-additions:world:2025",
            "metric": "solar photovoltaic capacity additions",
            "period": "2025",
            "value": 600,
            "unit": "GW",
            "relation": "greater_than",
            "source_id": "iea-ger-2026-solar",
            "locator": "Technology: Solar PV and wind; 2025 capacity paragraph",
        },
        {
            "key": "iea:solar-pv-generation:world:2025",
            "metric": "solar photovoltaic electricity generation",
            "period": "2025",
            "value": 2700,
            "unit": "TWh",
            "relation": "approximately",
            "source_id": "iea-ger-2026-trends",
            "locator": "Global trends; Solar saw extraordinary growth in 2025",
        },
        {
            "key": "iea:solar-pv-generation-share:world:2025",
            "metric": "solar photovoltaic share of global electricity generation",
            "period": "2025",
            "value": 8,
            "unit": "percent",
            "relation": "greater_than",
            "source_id": "iea-ger-2026-trends",
            "locator": "Global trends; Solar saw extraordinary growth in 2025",
        },
    ]
    star = {
        "schema": "star-solar-star.definition.v1",
        "id": "global-solar-2025",
        "type": "global-solar",
        "name": "Global Solar 2025",
        "description": "Dated public observations are kept as separate source statements; differing scopes and estimates are not averaged.",
        "region": {"scheme": "UN_M49", "code": "001", "name": "World"},
        "sources": [
            source("irena-rsc-2026", "International Renewable Energy Agency", "Renewable Capacity Statistics 2026", IRENA_URL, "2026", accessed, irena_raw),
            iea_source("iea-ger-2026-solar", "Global Energy Review 2026: Technology—Solar PV and wind", IEA_SOLAR_URL, accessed, iea_solar_raw, iea_solar_evidence),
            iea_source("iea-ger-2026-trends", "Global Energy Review 2026: Global trends", IEA_TRENDS_URL, accessed, iea_trends_raw, iea_trends_evidence),
            source("globalgrid-solar-deployment", "GlobalGrid2050", "Global Solar PV Deployment 2025", GLOBALGRID_URL, "2026-09-14", accessed, estate_raw, role="estate context; numerical observations use IRENA/IEA only", commit=GLOBALGRID_COMMIT),
        ],
        "observations": observations,
        "seed": {
            "algorithm": "sha256",
            "canonicalization": CANONICALIZATION,
            "inputs": sorted(item["key"] for item in observations),
            "url_parameter": "seed",
            "value": seed_for(observations),
        },
    }
    validate(star)
    return star


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--accessed-utc")
    parser.add_argument("--allow-audited-iea-fixture-on-403", action="store_true")
    args = parser.parse_args()
    value = build(args.accessed_utc, args.allow_audited_iea_fixture_on_403)
    write_json(args.output, value)
    print(f"{args.output}: {args.output.stat().st_size} bytes sha256={digest(args.output.read_bytes())} seed={value['seed']['value']}")
