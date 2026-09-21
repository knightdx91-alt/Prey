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
        versions = {c["version"] for c in report["chunk_variants"]}
        self.assertEqual(versions, {0x746})
        headers = {c["header"] for c in report["chunk_variants"]}
        self.assertEqual(headers, {"legacy", "CrCh"})

    def test_signatures_are_deduplicated(self):
        """The same header shape across archives must be recorded once.

        This is what keeps the report flat as the install grows: a 41 GB game
        repeats a few hundred header shapes across tens of archives, and a
        second identical header teaches us nothing the first did not.
        """
        import shutil

        # A byte-identical copy of an archive adds occurrences, not signatures.
        copy = os.path.join(self.root, "GameSDK", "GameData_copy.pak")
        shutil.copy(self.game_pak, copy)

        report = self._report()
        self.assertEqual(report["totals"]["archives"], 3)

        keys = [s["key_hex"] for s in report["signatures"]]
        self.assertEqual(len(keys), len(set(keys)), "duplicate signature keys")

        # Every signature was seen at least twice now (original + copy).
        cgf = next(
            s for s in report["signatures"]
            if s["identified"] == "CryEngine chunked file (legacy header)"
        )
        self.assertEqual(cgf["count"], 2)
        self.assertEqual(len(cgf["examples"]), 2)
        self.assertIn(".cgf", cgf["extensions"])

    def test_chunk_variants_collapse_by_shape(self):
        """Two .cgf files of the same version are one variant, counted twice."""
        with zipfile.ZipFile(self.game_pak, "a", zipfile.ZIP_DEFLATED) as z:
            z.writestr("Objects/characters/phantom.cgf", CGF_LEGACY)

        report = self._report()
        legacy = [c for c in report["chunk_variants"] if c["header"] == "legacy"]
        self.assertEqual(len(legacy), 1)
        self.assertEqual(legacy[0]["count"], 2)

    def test_chunk_variant_drops_per_file_offsets(self):
        """Offsets differ per file and say nothing about the format variant."""
        report = self._report()
        for variant in report["chunk_variants"]:
            self.assertNotIn("chunk_table_offset", variant)
            self.assertNotIn("chunk_count", variant)

    def test_signature_examples_are_capped(self):
        registry = probe.Registry(examples_per_signature=2)
        for i in range(10):
            registry.add_sample(f"f{i}.dds", ".dds", 100, DDS)
        sig = registry.as_report()["signatures"][0]
        self.assertEqual(sig["count"], 10)
        self.assertEqual(len(sig["examples"]), 2)

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
        self.assertTrue(report["signatures"])
        for sig in report["signatures"]:
            self.assertLessEqual(len(sig["head_hex"]) // 2, probe.HEADER_BYTES)
            self.assertLessEqual(
                len(sig["key_hex"]) // 2, probe.SIGNATURE_KEY_BYTES
            )

    def test_archives_record_sample_counts(self):
        report = self._report()
        game = next(a for a in report["archives"] if a["path"].endswith("GameData.pak"))
        self.assertGreater(game["sampled"], 0)
        self.assertEqual(game["sample_errors"], 0)

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


class DigestTest(unittest.TestCase):
    """The digest is the paste-sized transfer channel; it must stay small
    without dropping the parts that matter."""

    def setUp(self) -> None:
        self.report = {
            "probe_version": 1,
            "install_name": "Prey",
            "platform": "Windows",
            "binaries": {"count": 40, "audio_middleware_detected": ["Wwise (via CryEngine ATL)"]},
            "archives": [{"lua": {"source": 120, "bytecode": 4}}],
            "totals": {
                "archives": 42, "archives_unreadable": 0, "total_entries": 118432,
                "uncompressed_size": 42_000_000_000, "compressed_size": 39_000_000_000,
                "entries_needing_crypak_decoding": 17,
                "methods": {"deflate": 118201, "store": 214, "deflate+encrypt": 17},
                "extensions": {f".ext{i}": 100 - i for i in range(50)},
            },
            "signatures": [
                {
                    "key_hex": f"{i:032x}", "head_hex": f"{i:0128x}",
                    "identified": None if i % 3 == 0 else "DirectDraw Surface",
                    "extensions": {".dds": 5}, "count": 200 - i,
                    "examples": [{"name": f"Textures/t{i}.dds", "size": 100}],
                }
                for i in range(120)
            ],
            "chunk_variants": [
                {"header": "legacy", "version": 1862, "file_type": 4294901760,
                 "extensions": {".cgf": 9}, "count": 8821, "examples": ["a.cgf"]},
            ],
        }

    def test_digest_is_paste_sized(self):
        text = probe.digest(self.report)
        self.assertLess(len(text), 20_000, "digest should stay pasteable")

    def test_digest_carries_the_headline_facts(self):
        text = probe.digest(self.report)
        for expected in ("PREY PROBE DIGEST", "install=Prey", "archives=42",
                         "Wwise (via CryEngine ATL)", "lua source=120 bytecode=4",
                         "crypak_only_entries=17", "deflate+encrypt",
                         "header=legacy version=1862", "END DIGEST"):
            self.assertIn(expected, text, expected)

    def test_signatures_are_capped_but_noted(self):
        text = probe.digest(self.report, top_sig=10)
        self.assertIn("top 10 of 120", text)
        self.assertIn("110 more", text)

    def test_unrecognized_section_is_never_truncated(self):
        """The unidentified formats are the work queue; losing them defeats
        the point of sending a digest at all."""
        text = probe.digest(self.report, top_sig=5)
        unknown = [s for s in self.report["signatures"] if not s["identified"]]
        self.assertIn(f"UNRECOGNIZED ({len(unknown)}, all listed)", text)
        for sig in unknown:
            self.assertIn(sig["key_hex"], text)

    def test_digest_handles_a_minimal_report(self):
        bare = {
            "probe_version": 1, "install_name": "x", "platform": "Linux",
            "binaries": {"count": 0, "audio_middleware_detected": ["UNDETERMINED"]},
            "archives": [], "signatures": [], "chunk_variants": [],
            "totals": {
                "archives": 0, "archives_unreadable": 0, "total_entries": 0,
                "uncompressed_size": 0, "compressed_size": 0,
                "entries_needing_crypak_decoding": 0, "methods": {}, "extensions": {},
            },
        }
        self.assertIn("END DIGEST", probe.digest(bare))

    def test_cli_writes_digest_to_file(self):
        import tempfile as _tf
        with _tf.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "Prey")
            os.makedirs(root)
            with zipfile.ZipFile(os.path.join(root, "a.pak"), "w") as z:
                z.writestr("Objects/m.cgf", CGF_LEGACY)
            out = os.path.join(tmp, "r.json")
            dig = os.path.join(tmp, "d.txt")
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                probe.main([root, "-o", out, "--digest", dig])
            with open(dig, encoding="utf-8") as fh:
                self.assertIn("PREY PROBE DIGEST", fh.read())
