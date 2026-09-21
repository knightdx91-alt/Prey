#!/usr/bin/env python3
"""Tests for device.

The interesting paths cannot run here -- there is no Android underneath -- so
the Android-specific parsing is exercised against captured-shape fixtures, and
the off-Android path is exercised for real.

    python3 -m unittest discover -s tools/device -v
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import device  # noqa: E402

GB = 1024 ** 3

# Shape of a real `getprop` dump, abbreviated.
GETPROP = """
[ro.product.manufacturer]: [samsung]
[ro.product.model]: [SM-F988B]
[ro.product.device]: [q2q]
[ro.build.version.release]: [16]
[ro.build.version.sdk]: [36]
[ro.product.cpu.abi]: [arm64-v8a]
[ro.board.platform]: [pineapple]
[ro.soc.model]: [SM8850]
[ro.hardware.egl]: [adreno]
[ro.opengles.version]: [196610]
[dalvik.vm.heapsize]: [512m]
[an.unrelated.property]: [ignored]
[malformed line without brackets]
"""


class PropsTest(unittest.TestCase):
    def test_parses_getprop_dump_into_groups(self):
        with mock.patch.object(device.shutil, "which", return_value="/system/bin/getprop"), \
                mock.patch.object(device, "run", return_value=GETPROP):
            props = device.read_props()

        self.assertEqual(props["identity"]["ro.product.model"], "SM-F988B")
        self.assertEqual(props["cpu"]["ro.product.cpu.abi"], "arm64-v8a")
        self.assertEqual(props["graphics"]["ro.hardware.egl"], "adreno")

    def test_ignores_properties_not_asked_for(self):
        with mock.patch.object(device.shutil, "which", return_value="/system/bin/getprop"), \
                mock.patch.object(device, "run", return_value=GETPROP):
            props = device.read_props()
        flat = {k for group in props.values() for k in group}
        self.assertNotIn("an.unrelated.property", flat)

    def test_no_getprop_yields_empty(self):
        with mock.patch.object(device.shutil, "which", return_value=None):
            self.assertEqual(device.read_props(), {})

    def test_malformed_lines_do_not_raise(self):
        with mock.patch.object(device.shutil, "which", return_value="x"), \
                mock.patch.object(device, "run", return_value="garbage\n[[[\n"):
            self.assertEqual(device.read_props(), {})


class GlesTest(unittest.TestCase):
    def test_decodes_packed_version(self):
        self.assertEqual(device.decode_gles("196610"), "3.2")  # 0x30002
        self.assertEqual(device.decode_gles("196608"), "3.0")

    def test_bad_input_returns_none(self):
        self.assertIsNone(device.decode_gles("not a number"))
        self.assertIsNone(device.decode_gles(None))


class GpuTest(unittest.TestCase):
    """Which GPU family this is decides whether Phase 2 is viable at all."""

    def _classify(self, *, egl="", vk_name="", soc=""):
        props = {"graphics": {"ro.hardware.egl": egl}, "cpu": {"ro.soc.model": soc}}
        return device.classify_gpu(props, {"device_name": vk_name})

    def test_adreno_from_egl_property(self):
        result = self._classify(egl="adreno")
        self.assertEqual(result["family"], "adreno")
        self.assertIn("Turnip", result["note"])

    def test_adreno_from_vulkan_device_name(self):
        self.assertEqual(self._classify(vk_name="Adreno (TM) 840")["family"], "adreno")

    def test_xclipse_is_distinguished_from_adreno(self):
        """Exynos parts have no mature open driver; the distinction matters."""
        result = self._classify(vk_name="Samsung Xclipse 950")
        self.assertEqual(result["family"], "xclipse")
        self.assertIn("vendor Vulkan", result["note"])

    def test_mali_recognized(self):
        self.assertEqual(self._classify(vk_name="Mali-G720")["family"], "mali")

    def test_unknown_is_admitted_not_guessed(self):
        result = self._classify()
        self.assertEqual(result["family"], "unknown")
        self.assertIn("vulkan-tools", result["note"])


class VulkanTest(unittest.TestCase):
    def test_missing_vulkaninfo_gives_actionable_hint(self):
        with mock.patch.object(device.shutil, "which", return_value=None):
            info = device.read_vulkan()
        self.assertFalse(info["available"])
        self.assertIn("pkg install vulkan-tools", info["hint"])

    def test_parses_summary_and_texture_formats(self):
        summary = """
        GPU0:
            apiVersion = 1.3.274
            driverVersion = 512.780.0
            deviceName = Adreno (TM) 840
            deviceType = PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU
            textureCompressionASTC_LDR = true
            textureCompressionETC2 = true
        """
        with mock.patch.object(device.shutil, "which", return_value="/usr/bin/vulkaninfo"), \
                mock.patch.object(device, "run", return_value=summary):
            info = device.read_vulkan()

        self.assertTrue(info["available"])
        self.assertEqual(info["api_version"], "1.3.274")
        self.assertEqual(info["device_name"], "Adreno (TM) 840")
        self.assertTrue(info["astc_ldr"])
        self.assertTrue(info["etc2"])
        self.assertFalse(info["bc"], "desktop BC should not be assumed present")


class StorageTest(unittest.TestCase):
    def test_deduplicates_same_filesystem(self):
        """~/storage/shared and /storage/emulated/0 are usually one filesystem."""
        usage = mock.Mock(total=256 * GB, free=100 * GB)
        with mock.patch.object(device.os.path, "isdir", return_value=True), \
                mock.patch.object(device.shutil, "disk_usage", return_value=usage):
            entries = device.read_storage()
        self.assertEqual(len(entries), 1)

    def test_skips_unreadable_paths(self):
        with mock.patch.object(device.os.path, "isdir", return_value=True), \
                mock.patch.object(device.shutil, "disk_usage", side_effect=OSError):
            self.assertEqual(device.read_storage(), [])


class DigestTest(unittest.TestCase):
    def _report(self, free_gb: float) -> dict:
        return {
            "is_android": True, "in_termux": True, "machine": "aarch64",
            "properties": {
                "identity": {"ro.product.model": "SM-F988B",
                             "ro.product.manufacturer": "samsung"},
                "os": {"ro.build.version.release": "16", "ro.build.version.sdk": "36"},
                "cpu": {"ro.product.cpu.abi": "arm64-v8a", "ro.soc.model": "SM8850"},
            },
            "cpu": {"cores": 8, "core_clusters": [4320, 3530, 2270]},
            "memory": {"MemTotal": 16 * GB, "MemAvailable": 9 * GB},
            "storage": [{"label": "shared", "path": "/storage/emulated/0",
                         "total": 512 * GB, "free": free_gb * GB}],
            "vulkan": {"available": True, "api_version": "1.3.274",
                       "device_name": "Adreno (TM) 840", "astc_ldr": True,
                       "astc_hdr": False, "bc": False, "etc2": True},
            "gpu": {"family": "adreno", "note": "Adreno — Turnip"},
            "opengl_es": "3.2",
        }

    def test_carries_the_decisive_facts(self):
        text = device.digest(self._report(200))
        for expected in ("PREY DEVICE DIGEST", "SM-F988B", "arm64-v8a",
                         "gpu_family=adreno", "vulkan=1.3.274", "astc_ldr=True",
                         "END DIGEST"):
            self.assertIn(expected, text, expected)

    def test_budget_check_passes_with_room(self):
        text = device.digest(self._report(200))
        self.assertNotIn("short by", text)

    def test_budget_check_reports_shortfall(self):
        """A nearly-full phone must say so, not quietly pass."""
        text = device.digest(self._report(8.0))
        self.assertIn("short by", text)
        # aggressive (6.7) fits in 8 GB; quality (20.9) does not.
        aggressive = next(l for l in text.splitlines() if "aggressive" in l)
        quality = next(l for l in text.splitlines() if "quality" in l)
        self.assertIn("fits", aggressive)
        self.assertIn("short by", quality)

    def test_flags_when_not_android(self):
        report = self._report(200)
        report["is_android"] = False
        self.assertIn("NOT ANDROID", device.digest(report))

    def test_missing_vulkan_is_reported_not_hidden(self):
        report = self._report(200)
        report["vulkan"] = {"available": False, "hint": "pkg install vulkan-tools"}
        text = device.digest(report)
        self.assertIn("vulkan=UNAVAILABLE", text)
        self.assertIn("pkg install vulkan-tools", text)

    def test_digest_survives_a_sparse_report(self):
        sparse = {
            "is_android": False, "machine": "x86_64", "properties": {},
            "cpu": {"cores": 4}, "memory": {}, "storage": [],
            "vulkan": {"available": False}, "gpu": {"family": "unknown", "note": ""},
        }
        self.assertIn("END DIGEST", device.digest(sparse))


class CliTest(unittest.TestCase):
    def test_writes_json_and_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "device.json")
            dig = os.path.join(tmp, "device.txt")
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(device.main(["-o", out, "--digest", dig]), 0)
            with open(out, encoding="utf-8") as fh:
                self.assertIn("is_android", json.load(fh))
            with open(dig, encoding="utf-8") as fh:
                self.assertIn("PREY DEVICE DIGEST", fh.read())

    def test_digest_to_stdout_by_default(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            device.main([])
        self.assertIn("PREY DEVICE DIGEST", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
