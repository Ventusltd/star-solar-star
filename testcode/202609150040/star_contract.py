#!/usr/bin/env python3
"""Dependency-free validator and seed compiler for public solar star definitions."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import ipaddress
import json
import math
import re
import urllib.parse
from pathlib import Path
from typing import Any


SCHEMA = "star-solar-star.definition.v1"
CANONICALIZATION = "UTF-8 JSON, recursively sorted object keys, observations sorted by key, no insignificant whitespace"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PERIOD = re.compile(r"^[0-9]{4}(?:-[0-9]{2}(?:-[0-9]{2})?)?$")
RELATIONS = {"exact", "approximately", "greater_than", "less_than"}
PUBLIC_LANGUAGE_EXCLUSIONS = (
    "companies house",
    "prospect company",
    "sales target",
    "karma",
    "vedic",
    "enemy",
    "verdict",
)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def seed_for(observations: list[dict[str, Any]]) -> str:
    ordered = sorted(observations, key=lambda item: item["key"])
    return hashlib.sha256(canonical_bytes(ordered)).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _date_like(value: Any, label: str) -> None:
    _require(isinstance(value, str) and PERIOD.fullmatch(value) is not None, f"{label} must be YYYY, YYYY-MM or YYYY-MM-DD")


def _public_https_url(value: Any, label: str) -> None:
    _require(isinstance(value, str), f"{label} must be a string")
    parsed = urllib.parse.urlsplit(value)
    _require(parsed.scheme == "https" and parsed.hostname is not None, f"{label} must use HTTPS with a host")
    _require(parsed.username is None and parsed.password is None, f"{label} must not contain credentials")
    _require(not parsed.fragment, f"{label} must not contain a fragment")
    host = parsed.hostname.lower().rstrip(".")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        _require("." in host and host != "localhost" and not host.endswith(".local"), f"{label} host must be public")
    else:
        _require(address.is_global, f"{label} IP host must be globally routable")


def validate(star: dict[str, Any]) -> dict[str, Any]:
    _require(isinstance(star, dict), "star must be a JSON object")
    required = {"schema", "id", "type", "name", "description", "region", "sources", "observations", "seed"}
    _require(required <= set(star), f"missing top-level keys: {sorted(required - set(star))}")
    _require(star["schema"] == SCHEMA, f"schema must be {SCHEMA}")
    _require(isinstance(star["id"], str) and SLUG.fullmatch(star["id"]) is not None, "id must be a lowercase hyphenated slug")
    _require(star["type"] in {"country-solar", "global-solar"}, "unsupported star type")
    _require(isinstance(star["name"], str) and 1 <= len(star["name"].strip()) <= 120, "name must contain 1 to 120 characters")
    _require(isinstance(star["description"], str) and 1 <= len(star["description"].strip()) <= 500, "description must contain 1 to 500 characters")

    public_text = " ".join([star["name"], star["description"]]).lower()
    for term in PUBLIC_LANGUAGE_EXCLUSIONS:
        _require(term not in public_text, f"public-facing name/description contains excluded term: {term}")

    region = star["region"]
    _require(isinstance(region, dict), "region must be an object")
    _require(set(region) == {"scheme", "code", "name"}, "region must contain scheme, code and name only")
    if star["type"] == "country-solar":
        _require(region["scheme"] == "ISO_3166-1_alpha-2", "country stars require ISO 3166-1 alpha-2")
        _require(re.fullmatch(r"[A-Z]{2}", str(region["code"])) is not None, "country code must be two uppercase letters")
    else:
        _require(region["scheme"] == "UN_M49" and region["code"] == "001", "global star requires UN M49 code 001")

    sources = star["sources"]
    _require(isinstance(sources, list) and sources, "sources must be a non-empty array")
    source_ids = set()
    for pos, source in enumerate(sources):
        label = f"sources[{pos}]"
        needed = {"id", "publisher", "title", "url", "published", "accessed_utc", "bytes", "sha256"}
        _require(isinstance(source, dict) and needed <= set(source), f"{label} lacks required provenance")
        _require(source["id"] not in source_ids, f"duplicate source id {source['id']}")
        source_ids.add(source["id"])
        _public_https_url(source["url"], f"{label}.url")
        _date_like(source["published"], f"{label}.published")
        _require(isinstance(source["accessed_utc"], str) and source["accessed_utc"].endswith("Z"), f"{label}.accessed_utc must end in Z")
        try:
            dt.datetime.fromisoformat(source["accessed_utc"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{label}.accessed_utc is invalid") from exc
        _require(isinstance(source["bytes"], int) and not isinstance(source["bytes"], bool) and source["bytes"] > 0, f"{label}.bytes must be positive")
        _require(isinstance(source["sha256"], str) and SHA256.fullmatch(source["sha256"]) is not None, f"{label}.sha256 is invalid")

    observations = star["observations"]
    _require(isinstance(observations, list) and observations, "observations must be a non-empty array")
    keys = set()
    for pos, observation in enumerate(observations):
        label = f"observations[{pos}]"
        needed = {"key", "metric", "period", "value", "unit", "relation", "source_id", "locator"}
        _require(isinstance(observation, dict) and needed <= set(observation), f"{label} lacks required fields")
        _require(isinstance(observation["key"], str) and observation["key"], f"{label}.key is required")
        _require(observation["key"] not in keys, f"duplicate observation key {observation['key']}")
        keys.add(observation["key"])
        _date_like(observation["period"], f"{label}.period")
        value = observation["value"]
        _require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value), f"{label}.value must be finite")
        _require(isinstance(observation["unit"], str) and observation["unit"], f"{label}.unit is required")
        _require(observation["relation"] in RELATIONS, f"{label}.relation is unsupported")
        _require(observation["source_id"] in source_ids, f"{label} refers to unknown source")
        _require(isinstance(observation["locator"], str) and observation["locator"], f"{label}.locator is required")

    seed = star["seed"]
    _require(isinstance(seed, dict), "seed must be an object")
    _require(seed.get("algorithm") == "sha256", "seed algorithm must be sha256")
    _require(seed.get("canonicalization") == CANONICALIZATION, "unexpected seed canonicalization")
    _require(seed.get("url_parameter") == "seed", "seed URL parameter must be seed")
    expected_inputs = sorted(keys)
    _require(seed.get("inputs") == expected_inputs, "seed inputs must be all observation keys in sorted order")
    expected_seed = seed_for(observations)
    _require(seed.get("value") == expected_seed, "seed does not match canonical observations")
    return {
        "id": star["id"],
        "type": star["type"],
        "region": region["code"],
        "sources": len(sources),
        "observations": len(observations),
        "seed": expected_seed,
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("star", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(json.loads(args.star.read_text(encoding="utf-8"))), sort_keys=True))
