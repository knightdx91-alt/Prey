#!/usr/bin/env python3
"""paktool — inspect and extract CryPak (``.pak``) archives.

CryPak archives are ZIP containers, but CryEngine does not restrict itself to
what a stock ZIP reader handles: it writes its own end-of-central-directory
record, uses compression methods outside the standard set, and has supported
per-file encryption. Python's :mod:`zipfile` refuses the whole archive when it
meets any of that.

This tool parses the central directory itself so that an archive with awkward
entries still yields everything readable, and so that the awkward entries get
*named* rather than collapsed into one exception. Finding out precisely which
entries a standard reader cannot touch is the point — see
``docs/ASSET_FORMATS.md``.

Usage:
    paktool.py list    <archive> [-p PATTERN] [-l]
    paktool.py stats   <archive>
    paktool.py extract <archive> -o OUTDIR [-p PATTERN] [-n]
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import struct
import sys
import zlib
from dataclasses import dataclass
from typing import BinaryIO, Iterator

SIG_EOCD = b"PK\x05\x06"
SIG_EOCD64 = b"PK\x06\x06"
SIG_LOCATOR64 = b"PK\x06\x07"
SIG_CENTRAL = b"PK\x01\x02"
SIG_LOCAL = b"PK\x03\x04"

EOCD_FIXED = 22
CENTRAL_FIXED = 46
LOCAL_FIXED = 30

# Standard ZIP methods, plus the CryEngine additions. The names above 8 come
# from CryEngine's ZipFileFormat.h and are UNVERIFIED against Prey specifically
# -- treat a hit on one of these as something to go and look at, not as a fact.
METHODS = {
    0: "store",
    8: "deflate",
    11: "store+streamcipher_keytable",
    12: "deflate+streamcipher_keytable",
    13: "deflate+encrypt",
    14: "deflate+streamcipher",
}

# Methods this tool can actually decompress.
READABLE = {0, 8}

FLAG_ENCRYPTED = 0x0001


class PakError(Exception):
    """The archive could not be parsed at all."""


# Upper byte of "version made by" is the host system of the writing tool.
# Different ZIP writers leave different values, which is what makes this a
# usable fingerprint for "was this archive rebuilt by something else?".
HOST_SYSTEMS = {
    0: "fat", 1: "amiga", 3: "unix", 7: "macintosh", 10: "ntfs",
    11: "mvs", 14: "vfat", 19: "osx",
}


@dataclass
class Entry:
    name: str
    method: int
    flags: int
    crc32: int
    comp_size: int
    uncomp_size: int
    local_offset: int
    version_made_by: int = 0
    dos_time: int = 0
    dos_date: int = 0

    @property
    def host_system(self) -> str:
        code = self.version_made_by >> 8
        return HOST_SYSTEMS.get(code, f"unknown({code})")

    @property
    def zip_version(self) -> str:
        return f"{(self.version_made_by & 0xFF) / 10:.1f}"

    @property
    def writer_signature(self) -> str:
        """Host system plus ZIP spec version -- a coarse fingerprint of the
        tool that wrote this entry. Retail archives are written once by the
        publisher's packer, so a mix of signatures in one install is a strong
        hint that something repacked it."""
        return f"{self.host_system}/{self.zip_version}"

    @property
    def mtime(self) -> str | None:
        """Entry timestamp, decoded from the DOS date/time fields."""
        if not self.dos_date:
            return None
        year = ((self.dos_date >> 9) & 0x7F) + 1980
        month = (self.dos_date >> 5) & 0x0F
        day = self.dos_date & 0x1F
        hour = (self.dos_time >> 11) & 0x1F
        minute = (self.dos_time >> 5) & 0x3F
        second = (self.dos_time & 0x1F) * 2
        if not (1 <= month <= 12 and 1 <= day <= 31):
            return None
        return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}"

    @property
    def method_name(self) -> str:
        return METHODS.get(self.method, f"unknown({self.method})")

    @property
    def encrypted(self) -> bool:
        return bool(self.flags & FLAG_ENCRYPTED) or self.method in (11, 12, 13, 14)

    @property
    def readable(self) -> bool:
        return self.method in READABLE and not self.encrypted

    @property
    def is_dir(self) -> bool:
        return self.name.endswith("/")

    @property
    def ext(self) -> str:
        base = self.name.rsplit("/", 1)[-1]
        _, dot, ext = base.rpartition(".")
        return ("." + ext.lower()) if dot else "<none>"


def _read_at(fh: BinaryIO, offset: int, size: int) -> bytes:
    fh.seek(offset)
    data = fh.read(size)
    if len(data) != size:
        raise PakError(f"short read at {offset:#x}: wanted {size}, got {len(data)}")
    return data


def _find_eocd(fh: BinaryIO, file_size: int) -> tuple[int, bytes]:
    """Scan backwards for the end-of-central-directory record.

    The ZIP comment may be up to 64 KiB, so the record can sit that far from
    the end. Scanning backwards finds the *last* one, which is what a reader
    should honour when an archive carries more than one.
    """
    window = min(file_size, 0xFFFF + EOCD_FIXED)
    start = file_size - window
    blob = _read_at(fh, start, window)
    pos = blob.rfind(SIG_EOCD)
    if pos < 0:
        raise PakError("no end-of-central-directory record; not a ZIP/CryPak archive")
    return start + pos, blob[pos : pos + EOCD_FIXED]


def _locate_central_directory(
    fh: BinaryIO, file_size: int
) -> tuple[int, int, int, int]:
    """Return ``(cd_offset, cd_size, entry_count, eocd_offset)``.

    Resolves the ZIP64 records when the 32-bit fields are saturated.
    """
    eocd_offset, eocd = _find_eocd(fh, file_size)
    # EOCD from offset 10: total entries (H), cd size (I), cd offset (I).
    count, cd_size, cd_offset = struct.unpack_from("<HII", eocd, 10)

    needs64 = 0xFFFFFFFF in (cd_size, cd_offset) or count == 0xFFFF
    if needs64 and eocd_offset >= 20:
        locator = _read_at(fh, eocd_offset - 20, 20)
        if locator.startswith(SIG_LOCATOR64):
            (eocd64_offset,) = struct.unpack_from("<Q", locator, 8)
            rec = _read_at(fh, eocd64_offset, 56)
            if rec.startswith(SIG_EOCD64):
                count, cd_size, cd_offset = struct.unpack_from("<QQQ", rec, 32)

    return cd_offset, cd_size, count, eocd_offset


def _parse_central_directory(blob: bytes, delta: int) -> Iterator[Entry]:
    """Walk central directory records, applying ``delta`` to local offsets."""
    pos = 0
    end = len(blob)
    while pos + CENTRAL_FIXED <= end:
        if blob[pos : pos + 4] != SIG_CENTRAL:
            break
        (
            version_made_by,
            _version_needed,
            flags,
            method,
            dos_time,
            dos_date,
            crc32,
            comp_size,
            uncomp_size,
            name_len,
            extra_len,
            comment_len,
            local_offset,
        ) = struct.unpack_from("<xxxxHHHHHHIIIHHHxxxxxxxxI", blob, pos)

        name_at = pos + CENTRAL_FIXED
        raw_name = blob[name_at : name_at + name_len]
        extra = blob[name_at + name_len : name_at + name_len + extra_len]

        if 0xFFFFFFFF in (uncomp_size, comp_size, local_offset):
            uncomp_size, comp_size, local_offset = _apply_zip64_extra(
                extra, uncomp_size, comp_size, local_offset
            )

        # CryEngine writes UTF-8 names; surrogateescape keeps a malformed name
        # round-trippable instead of aborting the walk over one bad entry.
        name = raw_name.decode("utf-8", "surrogateescape").replace("\\", "/")

        yield Entry(
            name=name,
            method=method,
            flags=flags,
            crc32=crc32,
            comp_size=comp_size,
            uncomp_size=uncomp_size,
            local_offset=local_offset + delta,
            version_made_by=version_made_by,
            dos_time=dos_time,
            dos_date=dos_date,
        )
        pos = name_at + name_len + extra_len + comment_len


def _apply_zip64_extra(
    extra: bytes, uncomp: int, comp: int, offset: int
) -> tuple[int, int, int]:
    """Replace 0xFFFFFFFF placeholders from the ZIP64 extended-info field.

    The 64-bit values appear in a fixed order but only for the fields that were
    actually saturated, so which ones are present depends on the placeholders.
    """
    pos = 0
    while pos + 4 <= len(extra):
        header_id, size = struct.unpack_from("<HH", extra, pos)
        body = extra[pos + 4 : pos + 4 + size]
        pos += 4 + size
        if header_id != 0x0001:
            continue
        cursor = 0

        def take() -> int | None:
            nonlocal cursor
            if cursor + 8 > len(body):
                return None
            (value,) = struct.unpack_from("<Q", body, cursor)
            cursor += 8
            return value

        for saturated, setter in (
            (uncomp == 0xFFFFFFFF, "uncomp"),
            (comp == 0xFFFFFFFF, "comp"),
            (offset == 0xFFFFFFFF, "offset"),
        ):
            if not saturated:
                continue
            value = take()
            if value is None:
                break
            if setter == "uncomp":
                uncomp = value
            elif setter == "comp":
                comp = value
            else:
                offset = value
        break
    return uncomp, comp, offset


class Pak:
    """A parsed CryPak archive."""

    def __init__(self, path: str):
        self.path = path
        self.fh: BinaryIO = open(path, "rb")
        try:
            self._parse()
        except BaseException:
            # A file that fails to parse must not leak its handle: callers see
            # only the exception, so they never get a chance to close it.
            self.fh.close()
            raise

    def _parse(self) -> None:
        self.size = os.fstat(self.fh.fileno()).st_size
        if self.size < EOCD_FIXED:
            raise PakError(f"file is too small to be an archive ({self.size} bytes)")

        cd_offset, cd_size, count, eocd_offset = _locate_central_directory(
            self.fh, self.size
        )

        # An archive with data prepended (a self-extracting stub, or a CryPak
        # header) reports offsets relative to a start that is no longer zero.
        # The central directory ends where the EOCD begins, so its true start is
        # known: recover the shift and apply it to every local header offset.
        self.offset_delta = 0
        if 0 < cd_size <= eocd_offset:
            actual = eocd_offset - cd_size
            if actual != cd_offset:
                self.offset_delta = actual - cd_offset
                cd_offset = actual

        if not (0 <= cd_offset <= self.size):
            raise PakError(f"central directory offset {cd_offset:#x} is outside the file")

        blob = _read_at(self.fh, cd_offset, min(cd_size, self.size - cd_offset))
        self.entries = list(_parse_central_directory(blob, self.offset_delta))
        self.declared_count = count

    def close(self) -> None:
        self.fh.close()

    def __enter__(self) -> "Pak":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def read(self, entry: Entry) -> bytes:
        """Decompress one entry. Raises :class:`PakError` if it cannot."""
        if entry.encrypted:
            raise PakError(f"encrypted ({entry.method_name})")
        if entry.method not in READABLE:
            raise PakError(f"unsupported compression method {entry.method_name}")

        header = _read_at(self.fh, entry.local_offset, LOCAL_FIXED)
        if not header.startswith(SIG_LOCAL):
            raise PakError(f"no local header at {entry.local_offset:#x}")
        name_len, extra_len = struct.unpack_from("<HH", header, 26)

        data_at = entry.local_offset + LOCAL_FIXED + name_len + extra_len
        raw = _read_at(self.fh, data_at, entry.comp_size)

        if entry.method == 0:
            out = raw
        else:
            out = zlib.decompress(raw, -zlib.MAX_WBITS)

        if entry.uncomp_size and len(out) != entry.uncomp_size:
            raise PakError(
                f"size mismatch: expected {entry.uncomp_size}, got {len(out)}"
            )
        if entry.crc32 and zlib.crc32(out) & 0xFFFFFFFF != entry.crc32:
            raise PakError("CRC mismatch")
        return out


def _human(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GiB"


def _safe_relative(name: str) -> str | None:
    """Reduce an archive entry name to a safe relative path, or reject it.

    Archive names are attacker-controlled. Two things have to go before the
    name touches the filesystem:

    - **Leading separators**, which would make the path absolute.
    - **A Windows drive prefix.** ``os.path.join(out, "C:/x")`` yields
      ``C:/x`` on Windows, because a drive-absolute component discards
      everything before it. That escapes the output directory outright, and a
      POSIX-only check never sees it.
    """
    candidate = name.replace("\\", "/").lstrip("/")
    # Strip any drive prefix, including one hiding behind a traversal segment.
    candidate = re.sub(r"^[A-Za-z]:[/\\]*", "", candidate)
    if not candidate or candidate.startswith("/"):
        return None
    if re.match(r"^[A-Za-z]:", candidate):
        return None
    return candidate


def _select(entries: list[Entry], pattern: str | None) -> list[Entry]:
    files = [e for e in entries if not e.is_dir]
    if not pattern:
        return files
    lowered = pattern.lower()
    return [e for e in files if fnmatch.fnmatch(e.name.lower(), lowered)]


def cmd_list(args: argparse.Namespace) -> int:
    with Pak(args.archive) as pak:
        chosen = _select(pak.entries, args.pattern)
        for e in chosen:
            if args.long:
                flag = " " if e.readable else "!"
                print(
                    f"{flag} {e.uncomp_size:>12} {e.comp_size:>12} "
                    f"{e.method_name:<30} {e.name}"
                )
            else:
                print(e.name)
        if args.long:
            print(f"\n{len(chosen)} file(s); '!' marks entries this tool cannot decode")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    with Pak(args.archive) as pak:
        files = [e for e in pak.entries if not e.is_dir]
        total_u = sum(e.uncomp_size for e in files)
        total_c = sum(e.comp_size for e in files)

        print(f"archive      {pak.path}")
        print(f"size         {_human(pak.size)}")
        print(f"entries      {len(files)} files "
              f"({len(pak.entries) - len(files)} directory records)")
        if pak.declared_count != len(pak.entries):
            print(f"             note: EOCD declared {pak.declared_count}")
        if pak.offset_delta:
            print(f"offset shift {pak.offset_delta:+d} bytes (data prepended)")
        print(f"uncompressed {_human(total_u)}")
        print(f"compressed   {_human(total_c)}"
              + (f"  ({100 * total_c / total_u:.1f}%)" if total_u else ""))

        methods: dict[str, int] = {}
        for e in files:
            methods[e.method_name] = methods.get(e.method_name, 0) + 1
        print("\ncompression methods")
        for name, count in sorted(methods.items(), key=lambda kv: -kv[1]):
            mark = "" if name in ("store", "deflate") else "   <-- needs CryPak handling"
            print(f"  {count:>8}  {name}{mark}")

        exts: dict[str, list[int]] = {}
        for e in files:
            bucket = exts.setdefault(e.ext, [0, 0])
            bucket[0] += 1
            bucket[1] += e.uncomp_size
        print("\nextensions (top 25 by count)")
        ranked = sorted(exts.items(), key=lambda kv: -kv[1][0])[:25]
        for ext, (count, size) in ranked:
            print(f"  {count:>8}  {ext:<12} {_human(size):>10}")
        if len(exts) > 25:
            print(f"  ... and {len(exts) - 25} more extension(s)")

        blocked = [e for e in files if not e.readable]
        if blocked:
            print(f"\n{len(blocked)} entry(ies) need CryPak-aware decoding, e.g.:")
            for e in blocked[:10]:
                print(f"  {e.method_name:<30} {e.name}")
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    out_root = os.path.abspath(args.output)
    failures: list[tuple[str, str]] = []
    written = 0

    with Pak(args.archive) as pak:
        chosen = _select(pak.entries, args.pattern)
        for e in chosen:
            # Refuse absolute paths and traversal before touching the filesystem.
            rel = _safe_relative(e.name)
            if rel is None:
                failures.append((e.name, "unsafe path, skipped"))
                continue
            dest = os.path.abspath(os.path.join(out_root, rel))
            try:
                inside = os.path.commonpath([out_root, dest]) == out_root
            except ValueError:
                # Windows raises when the paths are on different drives, which
                # is itself the answer: the destination escaped out_root.
                inside = False
            if not inside:
                failures.append((e.name, "unsafe path, skipped"))
                continue

            if args.dry_run:
                print(f"would write {dest}")
                written += 1
                continue

            try:
                data = pak.read(e)
            except (PakError, zlib.error) as exc:
                failures.append((e.name, str(exc)))
                continue

            os.makedirs(os.path.dirname(dest) or out_root, exist_ok=True)
            with open(dest, "wb") as out:
                out.write(data)
            written += 1

    verb = "would extract" if args.dry_run else "extracted"
    print(f"{verb} {written} file(s) to {out_root}", file=sys.stderr)
    if failures:
        print(f"{len(failures)} failed:", file=sys.stderr)
        for name, why in failures[:20]:
            print(f"  {name}: {why}", file=sys.stderr)
        if len(failures) > 20:
            print(f"  ... and {len(failures) - 20} more", file=sys.stderr)
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="paktool", description="Inspect and extract CryPak (.pak) archives."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list archive contents")
    p_list.add_argument("archive")
    p_list.add_argument("-p", "--pattern", help="glob filter, e.g. '*.cgf'")
    p_list.add_argument("-l", "--long", action="store_true", help="sizes and methods")
    p_list.set_defaults(func=cmd_list)

    p_stats = sub.add_parser("stats", help="summarize an archive")
    p_stats.add_argument("archive")
    p_stats.set_defaults(func=cmd_stats)

    p_ex = sub.add_parser("extract", help="extract files")
    p_ex.add_argument("archive")
    p_ex.add_argument("-o", "--output", required=True, help="destination directory")
    p_ex.add_argument("-p", "--pattern", help="glob filter, e.g. 'Textures/*'")
    p_ex.add_argument("-n", "--dry-run", action="store_true")
    p_ex.set_defaults(func=cmd_extract)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except PakError as exc:
        print(f"paktool: {args.archive}: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"paktool: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
