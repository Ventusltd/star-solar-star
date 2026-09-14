import datetime as dt
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_sun.py")
SPEC = importlib.util.spec_from_file_location("build_sun_candidate", MODULE_PATH)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)

MERGE_SPEC = importlib.util.spec_from_file_location("merge_candidate_results", Path(__file__).with_name("merge_results.py"))
merger = importlib.util.module_from_spec(MERGE_SPEC)
MERGE_SPEC.loader.exec_module(merger)


class SunBuilderTests(unittest.TestCase):
    def test_pvlive_seed_is_order_independent_and_full_sha256(self):
        payload = {
            "meta": ["gsp_id", "datetime_gmt", "generation_mw", "installedcapacity_mwp"],
            "data": [
                [0, "2026-09-14T00:30:00Z", 2.0, 10.0],
                [0, "2026-09-14T00:00:00Z", 1.0, 10.0],
            ],
        }
        today, history = builder.parse_pvlive(payload, dt.date(2026, 9, 14))
        expected = builder.sha256(builder.canonical_json([
            ["2026-09-14T00:00:00Z", 1.0],
            ["2026-09-14T00:30:00Z", 2.0],
        ]))
        self.assertEqual(today["seed_sha256"], expected)
        self.assertEqual(len(today["seed_sha256"]), 64)
        self.assertEqual(today["energy_mwh"], 1.5)
        self.assertFalse(today["complete"])
        self.assertEqual(history["days"][0]["series"][0]["generation_mw"], 1.0)

    def test_pipeline_keeps_missing_geometry_explicit(self):
        source = {
            "generation": "fixture",
            "fields": ["repd_ref", "gg_project_id", "name", "technology", "status", "capacity_mw", "county", "region", "operator", "geometry_status", "latitude", "longitude"],
            "dictionaries": {
                "technology": ["Solar Photovoltaics", "Wind"],
                "status": ["Operational"],
                "county": ["Kent"],
                "region": ["South East"],
                "operator": ["Example"],
                "geometry_status": ["present", "missing"],
            },
            "rows": [
                ["1", "GG-1", "Has point", 0, 0, 12.5, 0, 0, 0, 0, 51.0, -1.0],
                ["2", "GG-2", "No point", 0, 0, 0, 0, 0, 0, 1, "", ""],
                ["3", "GG-3", "Wind", 1, 0, 100, 0, 0, 0, 0, 52.0, -2.0],
            ],
        }
        result = builder.build_uk_solar(json.dumps(source).encode())
        self.assertEqual(result["solar_projects"], 2)
        self.assertEqual(result["with_coordinates"], 1)
        self.assertEqual(result["missing_coordinate_repd_refs"], ["2"])
        self.assertEqual(result["solar_capacity_mw"], 12.5)
        self.assertEqual(result["projects"][0]["deep_link"].split("?")[1], "repd_ref=1")

    def test_markdown_tables_remain_source_strings(self):
        scan = builder.parse_markdown_scan("# Title\n\n| Country | GW |\n|---|---:|\n| UK | 22 |\n")
        self.assertEqual(scan["headings"][0]["text"], "Title")
        self.assertEqual(scan["tables"][0]["rows"][0], {"Country": "UK", "GW": "22"})

    def test_feed_retains_metadata_only(self):
        raw = b"""<rss><channel><item><title>A &amp; B</title><link>https://example.test/a</link><pubDate>date</pubDate><description>copyright text</description></item></channel></rss>"""
        rows = builder.parse_feed(raw, "Example", "https://example.test/feed")
        self.assertEqual(rows, [{"title": "A & B", "link": "https://example.test/a", "published": "date", "attribution": "Example"}])
        self.assertNotIn("description", rows[0])

    def test_robot_disallow_is_fail_closed(self):
        raw = b"User-agent: *\nDisallow: /feed\n"
        self.assertFalse(builder.robots_allows(raw, "https://example.test/robots.txt", "https://example.test/feed"))

    def test_writer_uses_stable_json_format(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "x.json"
            builder.write_json(path, {"b": 1, "a": 2})
            self.assertEqual(path.read_text(), '{\n  "a": 2,\n  "b": 1\n}\n')

    def test_lane_merge_fails_closed_on_divergence(self):
        local = {"lane": "local", "code_commit": "working-tree", "files": {"x": {"sha256": "a"}}, "facts": {"count": 1}}
        ci = {"lane": "ci", "code_commit": "abc", "files": {"x": {"sha256": "a"}}, "facts": {"count": 1}}
        self.assertEqual(merger.merge(local, ci)["status"], "matching")
        ci["facts"]["count"] = 2
        with self.assertRaisesRegex(ValueError, "facts differ"):
            merger.merge(local, ci)


if __name__ == "__main__":
    unittest.main()
