"""Exercise published production modules, never historical candidate copies."""
import copy
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import build_sun as builder
import star_contract as contract
import validate_sun
from issue_to_star import publish


def pv_day(date=dt.date(2026, 9, 14)):
    start = dt.datetime.combine(date, dt.time(), dt.timezone.utc)
    return {"meta": ["gsp_id", "datetime_gmt", "generation_mw", "installedcapacity_mwp"],
            "data": [[0, (start + dt.timedelta(minutes=30*n)).strftime("%Y-%m-%dT%H:%M:%SZ"), 1.0, 10.0] for n in range(1, 49)]}


class ProductionIntegrity(unittest.TestCase):
    def test_imports_are_production(self):
        for module in (builder, contract, validate_sun):
            self.assertEqual(Path(module.__file__).parent, ROOT / "scripts")

    def test_legacy_reference_identity_and_immutable_publication(self):
        star = json.loads((ROOT / "stars/global-solar-2025.star.json").read_text())
        self.assertEqual(contract.validate(star)["seed"], "a8696b5b9286966a43af65e3556ff3805df60542ed08f6fbc841d7bfed92dffa")
        with tempfile.TemporaryDirectory() as temp:
            first = publish(star, Path(temp))
            original = first.read_bytes()
            self.assertEqual(publish(copy.deepcopy(star), Path(temp)).read_bytes(), original)
            star["description"] += " Updated."
            with self.assertRaises(FileExistsError):
                publish(star, Path(temp))

    def test_jcs_known_bytes_and_version(self):
        rows = [{"key": "a", "value": 1.0}, {"key": "A", "value": -0.0}, {"key": "small", "value": 1e-6}]
        expected = b'[{"key":"A","value":0},{"key":"a","value":1},{"key":"small","value":0.000001}]'
        self.assertEqual(contract.observation_bytes(rows, contract.JCS_CANONICALIZATION), expected)
        self.assertNotEqual(contract.seed_for(rows), contract.seed_for(rows, contract.JCS_CANONICALIZATION))
        self.assertEqual(contract.seed_for(rows, contract.JCS_CANONICALIZATION), contract.seed_for(rows[::-1], contract.JCS_CANONICALIZATION))
        with self.assertRaises(ValueError):
            contract.seed_for(rows, "unknown-version")

    def test_jcs_rejects_invalid_domain(self):
        for value in (float("inf"), float("nan"), 2**53, float(2**53), -(2**53), "\ud800"):
            with self.subTest(value=repr(value)), self.assertRaises((ValueError, UnicodeError)):
                contract.seed_for([{"key": "x", "value": value}], contract.JCS_CANONICALIZATION)

    def test_interval_end_day_and_reordering(self):
        payload = pv_day()
        today, history = builder.parse_pvlive(payload, dt.date(2026, 9, 14))
        self.assertEqual(today["energy_mwh"], 24)
        self.assertEqual(today["series"][0]["timestamp_utc"], "2026-09-14T00:30:00Z")
        self.assertEqual(today["series"][-1]["timestamp_utc"], "2026-09-15T00:00:00Z")
        payload["data"].reverse()
        self.assertEqual(builder.parse_pvlive(payload, dt.date(2026, 9, 14)), (today, history))

    def test_request_bounds_follow_official_interval_end_convention(self):
        from urllib.parse import parse_qs, urlsplit
        query = parse_qs(urlsplit(builder.pv_url(dt.date(2026, 9, 14), 2)).query)
        self.assertEqual(query["start"], ["2026-09-13T00:30:00Z"])
        self.assertEqual(query["end"], ["2026-09-15T00:00:00Z"])

    def test_duplicate_missing_and_off_grid_intervals_fail(self):
        changes = [lambda p: p["data"].__setitem__(1, p["data"][0]),
                   lambda p: p["data"].pop(),
                   lambda p: p["data"][0].__setitem__(1, "2026-09-14T00:31:00Z"),
                   lambda p: p["data"][0].__setitem__(1, "2026-09-14T00:30:00+00:00"),
                   lambda p: p["data"][0].__setitem__(0, 1)]
        for change in changes:
            payload = pv_day()
            change(payload)
            with self.assertRaises(ValueError):
                builder.parse_pvlive(payload, dt.date(2026, 9, 14))
        payload = pv_day()
        payload["data"] = [payload["data"][0]] * 48
        with self.assertRaisesRegex(ValueError, "duplicate"):
            builder.parse_pvlive(payload, dt.date(2026, 9, 14))

    def test_nonfinite_invalid_power_and_capacity_fail(self):
        for value in (None, True, "1", -1, float("inf"), float("nan")):
            for column in (2, 3):
                if value is None and column == 3:
                    continue
                payload = pv_day()
                payload["data"][0][column] = value
                with self.subTest(value=value, column=column), self.assertRaises(ValueError):
                    builder.parse_pvlive(payload, dt.date(2026, 9, 14))

    def test_fallback_distinguishes_requested_and_observation_dates(self):
        today, _ = builder.parse_pvlive(pv_day(), dt.date(2026, 9, 15))
        self.assertEqual(today["requested_date"], "2026-09-15")
        self.assertEqual(today["data_date"], "2026-09-14")
        self.assertTrue(today["used_latest_available"])
        with self.assertRaises(ValueError):
            builder.parse_pvlive(pv_day(), dt.date(2026, 9, 13))
        payload = pv_day(dt.date(2026, 9, 12))
        payload["data"] += pv_day()["data"]
        with self.assertRaisesRegex(ValueError, "missing UTC days"):
            builder.parse_pvlive(payload, dt.date(2026, 9, 14))

    def test_validator_recomputes_all_summary_fields(self):
        payloads = {name: json.loads((ROOT / "sun" / name).read_text()) for name in validate_sun.NAMES}
        today, history = builder.parse_pvlive(pv_day(), dt.date(2026, 9, 14))
        payloads["history.json"] = history
        payloads["today.json"] = {"schema": "star-solar-star.today.v2", "seed": today["seed_sha256"],
                                  "pv_live": today, "london_solar_geometry": {"date": "2026-09-14"}}
        with patch.object(validate_sun, "load", side_effect=lambda root, name: payloads[name]):
            self.assertEqual(validate_sun.validate(ROOT / "sun")["date"], "2026-09-14")
            for key, value in {"energy_mwh": 25, "seed_sha256": "0"*64, "intervals": 47,
                               "complete": False, "date": "2026-09-13", "peak_mw": 2,
                               "peak_at_utc": "2026-09-14T01:00:00Z"}.items():
                original = history["days"][0][key]
                history["days"][0][key] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    validate_sun.validate(ROOT / "sun")
                history["days"][0][key] = original
            for key, value in {"data_date": "2026-09-15", "requested_date": "2026-09-13", "used_latest_available": True}.items():
                original = today[key]
                today[key] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    validate_sun.validate(ROOT / "sun")
                today[key] = original
            original_seed = today["seed_sha256"]
            payloads["today.json"]["seed"] = today["seed_sha256"] = history["days"][0]["seed_sha256"] = "0"*64
            with self.assertRaisesRegex(ValueError, "recomputed series"):
                validate_sun.validate(ROOT / "sun")
            payloads["today.json"]["seed"] = today["seed_sha256"] = history["days"][0]["seed_sha256"] = original_seed
            # These rows are shared by today's selected day and history. Corrupting
            # both still fails recomputation, even though all declared seeds agree.
            today["series"][1]["timestamp_utc"] = today["series"][0]["timestamp_utc"]
            with self.assertRaisesRegex(ValueError, "unique ordered"):
                validate_sun.validate(ROOT / "sun")

    def test_preserves_real_project_null_geometry(self):
        projects = json.loads((ROOT / "sun/uk-solar.json").read_text())
        missing = [p["repd_ref"] for p in projects["projects"] if p["latitude"] is None or p["longitude"] is None]
        self.assertEqual(len(projects["projects"]), 3563)
        self.assertEqual(sorted(missing), ["14773", "1613", "1616", "17120", "17260"])


if __name__ == "__main__":
    unittest.main()
