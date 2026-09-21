#!/usr/bin/env python3
"""Tests for probe.

Builds a miniature Prey-shaped install at runtime and checks that the survey
answers the questions docs/ASSET_FORMATS.md is actually asking.

    python3 -m unittest discover -s tools/probe -v
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import probe  # noqa: E402

CGF_LEGACY = b"CryTek\x00\x00" + struct.pack("<III", 0xFFFF0000, 0x746, 3200) + b"\xAA" * 512
CHR_CRCH = b"CrCh" + struct.pack("<III", 0x746, 12, 900) + b"\xBB" * 512
DDS = b"DDS " + struct.pack("<I", 124) + b"\x00" * 512
MTL = b'<?xml version="1.0"?>\n<Material Shader="Illum"/>\n'
LUA_SRC = b"-- talos i\nlocal Player = {}\nreturn Player\n"
LUA_BC = b"\x1bLua\x51\x00\x01\x04" + b"\x00" * 128
BNK = b"BKHD" + b"\x00" * 256


class ProbeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "Prey")
        os.makedirs(os.path.join(self.root, "GameSDK", "Levels", "talos"))
        os.makedirs(os.path.join(self.root, "Bin64"))

        for name in ("Prey.exe", "CryAudioImplWwise.dll", "CrySystem.dll"):
            with open(os.path.join(self.root, "Bin64", name), "wb") as fh:
                fh.write(b"MZ\x90\x00" + b"\x00" * 256)

        self.game_pak = os.path.join(self.root, "GameSDK", "GameData.pak")
        with zipfile.ZipFile(self.game_pak, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("Objects/characters/mimic.cgf", CGF_LEGACY)
            z.writestr("Animations/human.chr", CHR_CRCH)
            z.writestr("Materials/glass.mtl", MTL)
            z.writestr("Scripts/entities/player.lua", LUA_SRC)
            z.writestr("Scripts/ai/mimic.lua", LUA_BC)
            z.writestr("Textures/hull.dds", DDS, zipfile.ZIP_STORED)
            z.writestr("sounds/main.bnk", BNK, zipfile.ZIP_STORED)

        with zipfile.ZipFile(
            os.path.join(self.root, "GameSDK", "Levels", "talos", "level.pak"), "w"
        ) as z:
            z.writestr("terrain/heightmap.dat", b"\x05" * 1024)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _report(self, *extra: str) -> dict:
        out = os.path.join(self.tmp.name, "report.json")
        # The CLI prints a summary; tests care about the JSON, not the noise.
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            rc = probe.main([self.root, "-o", out, *extra])
        self.assertEqual(rc, 0)
        with open(out, encoding="utf-8") as fh:
            return json.load(fh)

    # -- discovery -------------------------------------------------------

    def test_finds_all_archives(self):
        found = probe.find_archives(self.root)
        self.assertEqual(len(found), 2)
        self.assertTrue(all(p.endswith(".pak") for p in found))

    def test_detects_audio_middleware_from_atl_dll(self):
        """CryAudioImplWwise.dll settles the Wwise-or-FMOD question."""
        info = probe.survey_binaries(self.root)
        self.assertIn("Wwise (via CryEngine ATL)", info["audio_middleware_detected"])
        self.assertEqual(info["count"], 3)

    def test_audio_undetermined_when_no_hint(self):
        bare = os.path.join(self.tmp.name, "Bare")
        os.makedirs(bare)
        with open(os.path.join(bare, "Game.exe"), "wb") as fh:
            fh.write(b"MZ")
        self.assertEqual(
            probe.survey_binaries(bare)["audio_middleware_detected"], ["UNDETERMINED"]
        )

    def test_hint_does_not_match_mid_word(self):
        """The 'ak' hint must not fire on an unrelated name like 'bake.dll'."""
        bare = os.path.join(self.tmp.name, "Bare2")
        os.makedirs(bare)
        for name in ("bake.dll", "shakes.dll"):
            with open(os.path.join(bare, name), "wb") as fh:
                fh.write(b"MZ")
        self.assertEqual(
            probe.survey_binaries(bare)["audio_middleware_detected"], ["UNDETERMINED"]
        )

    # -- format identification -------------------------------------------

    def test_identifies_known_magics(self):
        self.assertEqual(probe.identify(DDS), "DirectDraw Surface")
        self.assertEqual(probe.identify(BNK), "Wwise SoundBank")
        self.assertEqual(probe.identify(LUA_BC), "Lua bytecode")
        self.assertIsNone(probe.identify(b"\x00\x01\x02\x03unrecognized"))

    def test_parses_both_chunk_header_layouts(self):
        legacy = probe.parse_chunk_header(CGF_LEGACY)
        self.assertEqual(legacy["header"], "legacy")
        self.assertEqual(legacy["version"], 0x746)
        self.assertEqual(legacy["chunk_table_offset"], 3200)

        crch = probe.parse_chunk_header(CHR_CRCH)
        self.assertEqual(crch["header"], "CrCh")
        self.assertEqual(crch["version"], 0x746)
        self.assertEqual(crch["chunk_count"], 12)

        self.assertIsNone(probe.parse_chunk_header(DDS))
        self.assertIsNone(probe.parse_chunk_header(b"CrCh"))  # truncated

    # -- survey ----------------------------------------------------------

    def test_report_captures_chunk_versions(self):
        report = self._report()
        versions = {
            c["version"]
            for a in report["archives"]
            for c in a.get("chunk_headers", [])
        }
        self.assertEqual(versions, {0x746})

    def test_report_separates_lua_source_from_bytecode(self):
        report = self._report()
        lua = next(a["lua"] for a in report["archives"] if "lua" in a)
        self.assertEqual(lua["source"], 1)
        self.assertEqual(lua["bytecode"], 1)

    def test_flags_cryengine_codec_without_losing_archive(self):
        """One custom-codec entry must be reported, not swallow the archive."""
        with open(self.game_pak, "rb") as fh:
            raw = bytearray(fh.read())
        pos = raw.find(b"PK\x01\x02")
        struct.pack_into("<H", raw, pos + 10, 12)  # deflate+streamcipher_keytable
        with open(self.game_pak, "wb") as fh:
            fh.write(raw)

        report = self._report()
        game = next(a for a in report["archives"] if a["path"].endswith("GameData.pak"))
        self.assertTrue(game["readable_as_zip"])
        self.assertEqual(game["unreadable_entries"], 1)
        self.assertIn("deflate+streamcipher_keytable", game["methods"])
        self.assertEqual(report["totals"]["entries_needing_crypak_decoding"], 1)

    def test_unreadable_archive_is_recorded_not_fatal(self):
        junk = os.path.join(self.root, "GameSDK", "broken.pak")
        with open(junk, "wb") as fh:
            fh.write(b"not a zip" * 50)

        report = self._report()
        broken = next(a for a in report["archives"] if a["path"].endswith("broken.pak"))
        self.assertFalse(broken["readable_as_zip"])
        self.assertIn("error", broken)
        self.assertEqual(report["totals"]["archives_unreadable"], 1)
        # The good archives still got surveyed.
        self.assertGreater(report["totals"]["total_entries"], 0)

    def test_totals_aggregate_across_archives(self):
        report = self._report()
        totals = report["totals"]
        self.assertEqual(totals["archives"], 2)
        self.assertEqual(totals["total_entries"], 8)
        self.assertIn(".cgf", totals["extensions"])
        self.assertEqual(totals["extensions"][".lua"], 2)

    # -- privacy ---------------------------------------------------------

    def test_report_contains_no_absolute_paths(self):
        """A Windows install path would carry the user's account name."""
        out = os.path.join(self.tmp.name, "report.json")
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            probe.main([self.root, "-o", out])
        with open(out, encoding="utf-8") as fh:
            text = fh.read()
        self.assertNotIn(self.root, text)
        self.assertNotIn(self.tmp.name, text)
        self.assertEqual(json.loads(text)["install_name"], "Prey")

    def test_samples_are_header_sized_only(self):
        """Samples must be signatures, not copies of asset content."""
        report = self._report()
        for archive in report["archives"]:
            for sample in archive.get("samples", []):
                if "head_hex" in sample:
                    self.assertLessEqual(
                        len(sample["head_hex"]) // 2, probe.HEADER_BYTES
                    )

    # -- listing ---------------------------------------------------------

    def test_optional_listing_is_written(self):
        import gzip

        listing = os.path.join(self.tmp.name, "files.txt.gz")
        self._report("--listing", listing)
        with gzip.open(listing, "rt", encoding="utf-8") as fh:
            lines = [ln for ln in fh.read().splitlines() if ln]
        self.assertEqual(len(lines), 8)
        self.assertTrue(all(ln.count("\t") == 2 for ln in lines))


if __name__ == "__main__":
    unittest.main()
