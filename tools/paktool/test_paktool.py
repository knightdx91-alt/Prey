#!/usr/bin/env python3
"""Tests for paktool.

Fixtures are generated at runtime with :mod:`zipfile`, so no binary blobs are
committed and no game data is needed to run these.

    python3 -m unittest discover -s tools/paktool -v
"""

from __future__ import annotations

import hashlib
import os
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paktool  # noqa: E402

FILES = {
    "Objects/alien/mimic.cgf": (b"CryTek\x00\x00" + b"\xAB" * 4000, zipfile.ZIP_DEFLATED),
    "Textures/hull_diff.dds": (b"DDS " + b"\x7F" * 2048, zipfile.ZIP_STORED),
    "Materials/glass.mtl": (b'<Material Shader="Glass"/>', zipfile.ZIP_DEFLATED),
    "Scripts/entities/player.lua": (b"-- talos i\nlocal p = {}\n", zipfile.ZIP_DEFLATED),
    "readme": (b"no extension here", zipfile.ZIP_STORED),
}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class PakToolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.basic = os.path.join(self.dir, "basic.pak")
        with zipfile.ZipFile(self.basic, "w") as z:
            for name, (data, method) in FILES.items():
                z.writestr(name, data, method)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _path(self, name: str) -> str:
        return os.path.join(self.dir, name)

    # -- parsing ---------------------------------------------------------

    def test_lists_every_entry(self):
        with paktool.Pak(self.basic) as pak:
            names = {e.name for e in pak.entries if not e.is_dir}
        self.assertEqual(names, set(FILES))

    def test_records_sizes_and_methods(self):
        with paktool.Pak(self.basic) as pak:
            by_name = {e.name: e for e in pak.entries}
        for name, (data, method) in FILES.items():
            entry = by_name[name]
            self.assertEqual(entry.uncomp_size, len(data), name)
            expected = "deflate" if method == zipfile.ZIP_DEFLATED else "store"
            self.assertEqual(entry.method_name, expected, name)
            self.assertTrue(entry.readable, name)

    def test_extension_classification(self):
        with paktool.Pak(self.basic) as pak:
            exts = {e.name: e.ext for e in pak.entries}
        self.assertEqual(exts["Objects/alien/mimic.cgf"], ".cgf")
        self.assertEqual(exts["readme"], "<none>")

    def test_rejects_non_archive(self):
        junk = self._path("junk.pak")
        with open(junk, "wb") as fh:
            fh.write(b"not a zip" * 100)
        with self.assertRaises(paktool.PakError):
            paktool.Pak(junk)

    # -- decompression ---------------------------------------------------

    def test_read_is_byte_identical(self):
        with paktool.Pak(self.basic) as pak:
            for entry in pak.entries:
                if entry.is_dir:
                    continue
                want, _ = FILES[entry.name]
                self.assertEqual(_digest(pak.read(entry)), _digest(want), entry.name)

    def test_zip64_entry(self):
        big_path = self._path("big.pak")
        payload = b"Z" * 200_000
        with zipfile.ZipFile(big_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            z.writestr("Levels/talos/terrain.dat", payload)
        with paktool.Pak(big_path) as pak:
            entry = next(e for e in pak.entries if not e.is_dir)
            self.assertEqual(entry.uncomp_size, len(payload))
            self.assertEqual(pak.read(entry), payload)

    # -- CryPak-specific behavior ----------------------------------------

    def test_recovers_offsets_when_data_is_prepended(self):
        """A CryPak header or stub before the ZIP shifts every local offset."""
        stub = b"CRYPAKSTUB" * 100
        shifted = self._path("prepended.pak")
        with open(self.basic, "rb") as src:
            body = src.read()
        with open(shifted, "wb") as fh:
            fh.write(stub + body)

        with paktool.Pak(shifted) as pak:
            self.assertEqual(pak.offset_delta, len(stub))
            for entry in pak.entries:
                if entry.is_dir:
                    continue
                want, _ = FILES[entry.name]
                self.assertEqual(pak.read(entry), want, entry.name)

    def test_unsupported_method_is_isolated_not_fatal(self):
        """One CryEngine-codec entry must not cost us the rest of the archive."""
        with open(self.basic, "rb") as src:
            raw = bytearray(src.read())
        pos = raw.find(b"PK\x01\x02")
        struct.pack_into("<H", raw, pos + 10, 13)  # METHOD_DEFLATE_AND_ENCRYPT
        odd = self._path("odd.pak")
        with open(odd, "wb") as fh:
            fh.write(raw)

        with paktool.Pak(odd) as pak:
            entries = [e for e in pak.entries if not e.is_dir]
            self.assertEqual(len(entries), len(FILES))

            blocked = [e for e in entries if not e.readable]
            self.assertEqual(len(blocked), 1)
            self.assertEqual(blocked[0].method_name, "deflate+encrypt")
            with self.assertRaises(paktool.PakError):
                pak.read(blocked[0])

            # Everything else still reads.
            for entry in entries:
                if entry.readable:
                    self.assertEqual(pak.read(entry), FILES[entry.name][0])

    def test_detects_corrupt_payload(self):
        with paktool.Pak(self.basic) as pak:
            entry = next(e for e in pak.entries if e.method_name == "store")
            pak.fh.seek(entry.local_offset + paktool.LOCAL_FIXED)
            # Flip a byte in the stored payload; the CRC check must notice.
            header = paktool._read_at(pak.fh, entry.local_offset, paktool.LOCAL_FIXED)
            name_len, extra_len = struct.unpack_from("<HH", header, 26)
            data_at = entry.local_offset + paktool.LOCAL_FIXED + name_len + extra_len
            with open(self.basic, "r+b") as fh:
                fh.seek(data_at)
                original = fh.read(1)
                fh.seek(data_at)
                fh.write(bytes([original[0] ^ 0xFF]))

        with paktool.Pak(self.basic) as pak:
            entry = next(e for e in pak.entries if e.method_name == "store")
            with self.assertRaises(paktool.PakError):
                pak.read(entry)

    # -- extraction ------------------------------------------------------

    def test_extract_writes_all_files(self):
        out = self._path("out")
        rc = paktool.main(["extract", self.basic, "-o", out])
        self.assertEqual(rc, 0)
        for name, (data, _) in FILES.items():
            with open(os.path.join(out, name), "rb") as fh:
                self.assertEqual(fh.read(), data, name)

    def test_extract_refuses_path_traversal(self):
        evil = self._path("evil.pak")
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("../../escaped.txt", b"nope")
            z.writestr("safe.txt", b"fine")

        out = os.path.join(self.dir, "nested", "out")
        rc = paktool.main(["extract", evil, "-o", out])

        self.assertEqual(rc, 1, "traversal entry should be reported as a failure")
        self.assertTrue(os.path.exists(os.path.join(out, "safe.txt")))
        self.assertFalse(os.path.exists(os.path.join(self.dir, "escaped.txt")))

    def test_extract_honours_pattern(self):
        out = self._path("filtered")
        rc = paktool.main(["extract", self.basic, "-o", out, "-p", "*.cgf"])
        self.assertEqual(rc, 0)
        written = [
            os.path.relpath(os.path.join(root, f), out)
            for root, _, files in os.walk(out)
            for f in files
        ]
        self.assertEqual(written, ["Objects/alien/mimic.cgf"])

    def test_dry_run_writes_nothing(self):
        out = self._path("dry")
        rc = paktool.main(["extract", self.basic, "-o", out, "-n"])
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
