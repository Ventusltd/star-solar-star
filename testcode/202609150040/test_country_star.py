from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from issue_to_star import extract  # noqa: E402
from star_contract import seed_for, validate  # noqa: E402
import build_global_star  # noqa: E402


class StarContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.star = json.loads((HERE / "global-solar.star.json").read_text(encoding="utf-8"))

    def test_global_record_validates(self):
        result = validate(self.star)
        self.assertEqual(result["observations"], 6)
        self.assertEqual(result["region"], "001")
        self.assertEqual(result["seed"], "a8696b5b9286966a43af65e3556ff3805df60542ed08f6fbc841d7bfed92dffa")

    def test_observation_order_does_not_change_seed(self):
        self.assertEqual(seed_for(self.star["observations"]), seed_for(list(reversed(self.star["observations"]))))

    def test_modified_measurement_is_rejected_without_new_seed(self):
        changed = copy.deepcopy(self.star)
        changed["observations"][0]["value"] += 1
        with self.assertRaisesRegex(ValueError, "seed does not match"):
            validate(changed)

    def test_private_work_language_is_rejected(self):
        changed = copy.deepcopy(self.star)
        changed["description"] = "A Companies House prospect company list"
        with self.assertRaisesRegex(ValueError, "excluded term"):
            validate(changed)

    def test_issue_parser_accepts_one_json_fence(self):
        body = "Proposal\n### Star JSON\n```json\n" + json.dumps(self.star) + "\n```\n"
        self.assertEqual(extract(body), self.star)

    def test_creator_is_mobile_and_deterministic(self):
        page = (HERE / "create" / "index.html").read_text(encoding="utf-8")
        self.assertIn('name="viewport"', page)
        self.assertIn("min-height:48px", page)
        self.assertIn("crypto.subtle.digest('SHA-256'", page)
        self.assertNotIn("Math.random", page)
        self.assertNotIn("decodeURIComponent(fromUrl)", page)
        for excluded in ("prospect company", "sales target", "verdict"):
            self.assertNotIn(excluded, page.lower())

    def test_iea_fixture_is_used_only_for_explicit_403_policy(self):
        error = urllib.error.HTTPError(build_global_star.IEA_SOLAR_URL, 403, "Forbidden", {}, None)
        with mock.patch.object(build_global_star, "fetch", side_effect=error):
            with self.assertRaises(urllib.error.HTTPError):
                build_global_star.iea_payload("iea-ger-2026-solar", build_global_star.IEA_SOLAR_URL, False)
            raw, text, evidence = build_global_star.iea_payload(
                "iea-ger-2026-solar", build_global_star.IEA_SOLAR_URL, True
            )
        self.assertIsNone(raw)
        self.assertIn("surpassing 600 GW", text)
        self.assertEqual(evidence["sha256"], "e132b601459dd69c1f60257a277905a8cdced445787c8ce201509f171e691fea")


if __name__ == "__main__":
    unittest.main()
