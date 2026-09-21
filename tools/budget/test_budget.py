#!/usr/bin/env python3
"""Tests for budget.

    python3 -m unittest discover -s tools/budget -v
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import budget  # noqa: E402

GB = budget.GB


class CategorizeTest(unittest.TestCase):
    def test_known_extensions(self):
        self.assertEqual(budget.categorize(".dds"), "texture")
        self.assertEqual(budget.categorize(".bnk"), "audio")
        self.assertEqual(budget.categorize(".cgf"), "geometry")
        self.assertEqual(budget.categorize(".bk2"), "video")
        self.assertEqual(budget.categorize(".lua"), "script")

    def test_split_mip_companions_count_as_texture(self):
        """CryEngine streams mips as .dds.1, .dds.2 -- which surface as .1, .2."""
        for ext in (".1", ".2", ".9"):
            self.assertEqual(budget.categorize(ext), "texture", ext)

    def test_unknown_falls_back_to_other(self):
        self.assertEqual(budget.categorize(".wibble"), "other")
        self.assertEqual(budget.categorize("<none>"), "other")

    def test_case_insensitive(self):
        self.assertEqual(budget.categorize(".DDS"), "texture")


class SplitTest(unittest.TestCase):
    def test_assumed_split_sums_to_one(self):
        self.assertAlmostEqual(sum(budget.ASSUMED_SPLIT.values()), 1.0, places=6)

    def test_sizes_from_total_preserves_total(self):
        sizes = budget.sizes_from_total(41 * GB)
        # Integer truncation per category, so allow a few bytes of slack.
        self.assertAlmostEqual(sum(sizes.values()) / GB, 41.0, places=3)

    def test_texture_dominates_the_assumption(self):
        sizes = budget.sizes_from_total(41 * GB)
        self.assertEqual(max(sizes, key=lambda k: sizes[k]), "texture")


class ModelTest(unittest.TestCase):
    def test_applies_factor_per_category(self):
        result = budget.model({"texture": 1000, "script": 1000}, "balanced")
        rows = {r["category"]: r for r in result["rows"]}
        self.assertEqual(rows["script"]["reduced"], 1000)  # factor 1.0
        self.assertLess(rows["texture"]["reduced"], 200)   # ~0.111
        self.assertEqual(result["total_before"], 2000)

    def test_rows_sorted_by_desktop_size(self):
        result = budget.model({"script": 10, "texture": 500, "audio": 100}, "balanced")
        order = [r["category"] for r in result["rows"]]
        self.assertEqual(order, ["texture", "audio", "script"])

    def test_profiles_are_ordered_by_aggressiveness(self):
        sizes = budget.sizes_from_total(41 * GB)
        totals = {p: budget.model(sizes, p)["total_after"] for p in budget.PROFILES}
        self.assertLess(totals["aggressive"], totals["balanced"])
        self.assertLess(totals["balanced"], totals["quality"])

    def test_every_profile_covers_every_category(self):
        categories = set(budget.ASSUMED_SPLIT)
        for name, profile in budget.PROFILES.items():
            missing = categories - set(profile["factors"])
            self.assertEqual(missing, set(), f"{name} missing {missing}")

    def test_factors_are_plausible(self):
        for name, profile in budget.PROFILES.items():
            for category, factor in profile["factors"].items():
                self.assertGreater(factor, 0.0, f"{name}/{category}")
                self.assertLessEqual(factor, 1.0, f"{name}/{category}")

    def test_ratio_is_reported(self):
        result = budget.model({"texture": 1000}, "balanced")
        self.assertGreater(result["ratio"], 1.0)

    def test_empty_input_does_not_divide_by_zero(self):
        result = budget.model({}, "balanced")
        self.assertEqual(result["total_after"], 0)
        self.assertEqual(result["ratio"], 0.0)


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, report: dict) -> str:
        path = os.path.join(self.tmp.name, "report.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report, fh)
        return path

    def test_apportions_archive_bytes_by_entry_count(self):
        report = {
            "archives": [{
                "readable_as_zip": True,
                "uncompressed_size": 1000,
                "extensions": {".dds": 3, ".lua": 1},
            }]
        }
        sizes = budget.sizes_from_report(report)
        self.assertEqual(sizes["texture"], 750)
        self.assertEqual(sizes["script"], 250)

    def test_sums_across_archives(self):
        report = {
            "archives": [
                {"readable_as_zip": True, "uncompressed_size": 100,
                 "extensions": {".dds": 1}},
                {"readable_as_zip": True, "uncompressed_size": 200,
                 "extensions": {".dds": 1}},
            ]
        }
        self.assertEqual(budget.sizes_from_report(report)["texture"], 300)

    def test_skips_unreadable_archives(self):
        report = {
            "archives": [
                {"readable_as_zip": False, "error": "bad"},
                {"readable_as_zip": True, "uncompressed_size": 100,
                 "extensions": {".dds": 1}},
            ]
        }
        self.assertEqual(budget.sizes_from_report(report), {"texture": 100})

    def test_archive_with_no_entries_is_skipped(self):
        report = {"archives": [
            {"readable_as_zip": True, "uncompressed_size": 100, "extensions": {}}
        ]}
        self.assertEqual(budget.sizes_from_report(report), {})

    def test_cli_rejects_empty_report(self):
        path = self._write({"archives": []})
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(budget.main(["--report", path]), 2)

    def test_cli_rejects_missing_file(self):
        with contextlib.redirect_stderr(io.StringIO()):
            rc = budget.main(["--report", os.path.join(self.tmp.name, "nope.json")])
        self.assertEqual(rc, 2)

    def test_cli_json_output(self):
        path = self._write({"archives": [{
            "readable_as_zip": True, "uncompressed_size": 1000,
            "extensions": {".dds": 1},
        }]})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(budget.main(["--report", path, "--json"]), 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(len(payload["results"]), 1)
        self.assertIn("total_after", payload["results"][0])

    def test_cli_all_profiles(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            budget.main(["--total-gb", "41", "--all-profiles", "--json"])
        payload = json.loads(buf.getvalue())
        self.assertEqual(len(payload["results"]), len(budget.PROFILES))


class RenderTest(unittest.TestCase):
    def test_units_adapt_to_magnitude(self):
        self.assertIn("GB", budget._size(5 * GB))
        self.assertIn("MB", budget._size(5 * 1024 ** 2))
        self.assertIn("KB", budget._size(5 * 1024))
        self.assertIn("B", budget._size(5))

    def test_small_totals_do_not_render_as_zero(self):
        """A tiny survey must not print a column of 0.00 GB."""
        rendered = budget._size(18 * 1024)
        self.assertNotIn("0.00", rendered)

    def test_headline_case_renders(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(budget.main(["--total-gb", "41"]), 0)
        out = buf.getvalue()
        self.assertIn("41.00 GB", out)
        self.assertIn("reduction:", out)
        self.assertIn("UNVERIFIED", out)


if __name__ == "__main__":
    unittest.main()


class PassthroughProfileTest(unittest.TestCase):
    """The target GPU supports BC, so Prey's shipped textures can be sampled
    without conversion. That makes a transcoder optional, and this profile is
    what prices that choice."""

    def test_texture_factor_is_pure_resolution(self):
        """BC stays BC, so bits-per-pixel is unchanged; only pixel count drops.
        Half each dimension = a quarter of the pixels = 0.25 exactly."""
        self.assertEqual(budget.PROFILES["passthrough"]["factors"]["texture"], 0.25)

    def test_costs_more_than_transcoding_but_still_reduces(self):
        sizes = budget.sizes_from_total(41 * GB)
        passthrough = budget.model(sizes, "passthrough")["total_after"]
        balanced = budget.model(sizes, "balanced")["total_after"]
        self.assertGreater(passthrough, balanced, "ASTC should beat BC on size")
        self.assertLess(passthrough, 41 * GB, "but it must still be a reduction")

    def test_lands_in_the_expected_range(self):
        sizes = budget.sizes_from_total(41 * GB)
        gb = budget.model(sizes, "passthrough")["total_after"] / GB
        self.assertTrue(11 < gb < 14, f"expected ~12.6 GB, got {gb:.1f}")

    def test_is_selectable_from_the_cli(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = budget.main(["--total-gb", "41", "--profile", "passthrough", "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(buf.getvalue())["results"][0]["profile"], "passthrough")

    def test_included_in_all_profiles_comparison(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            budget.main(["--total-gb", "41", "--all-profiles", "--json"])
        names = {r["profile"] for r in json.loads(buf.getvalue())["results"]}
        self.assertIn("passthrough", names)
