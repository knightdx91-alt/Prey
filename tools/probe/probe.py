#!/usr/bin/env python3
"""probe — survey a Prey install and emit a small, shareable report.

The game data cannot travel: an install is tens of gigabytes, and it is not
ours to copy anyway. But almost every open question in ``docs/ASSET_FORMATS.md``
is answerable from *metadata* — which archives exist, what extensions ship,
which compression methods appear, what the first bytes of each file type look
like, which audio middleware the shipped DLLs name.

That metadata is kilobytes. This tool walks an install you already own and
writes it to a single JSON file you can commit or paste back.

What it reads:  archive directories, file headers (64 bytes by default).
What it writes: counts, histograms, and short hex signatures.
What it never does: copy asset contents, or record absolute paths (which would
leak your username on Windows).

Usage:
    probe.py "C:/Program Files (x86)/Steam/steamapps/common/Prey" -o report.json
    probe.py /path/to/Prey -o report.json --listing files.txt.gz
"""

from __future__ import annotations

import argparse
import binascii
import collections
import datetime
import gzip
import json
import os
import platform
import struct
import sys
from typing import Any

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "paktool")
)

import paktool  # noqa: E402

PROBE_VERSION = 1

# Bytes sampled from the front of a file. Enough for a magic number and a
# version field; far too few to be a copy of anything.
HEADER_BYTES = 64

# Samples are deduplicated on their leading bytes, so the report scales with
# the number of *distinct formats* rather than with archives x extensions. 16
# bytes is the informative window for the formats that matter -- a .cgf legacy
# header is exactly signature(8) + file type(4) + version(4).
SIGNATURE_KEY_BYTES = 16

# CryEngine's Audio Translation Layer ships one implementation DLL per
# middleware, so the filename settles the Wwise-or-FMOD question outright.
AUDIO_IMPL_HINTS = {
    "cryaudioimplwwise": "Wwise (via CryEngine ATL)",
    "cryaudioimplfmod": "FMOD (via CryEngine ATL)",
    "cryaudioimplsdlmixer": "SDL_mixer (via CryEngine ATL)",
    "cryaudioimplportaudio": "PortAudio (via CryEngine ATL)",
    "fmod": "FMOD (direct)",
    "fmodstudio": "FMOD Studio (direct)",
    "wwise": "Wwise (direct)",
    "ak": "Wwise (AK* runtime)",
}

# Known container magics, for labelling sampled headers.
MAGICS: list[tuple[bytes, str]] = [
    (b"CryTek\x00\x00", "CryEngine chunked file (legacy header)"),
    (b"CrCh", "CryEngine chunked file (CrCh header)"),
    (b"DDS ", "DirectDraw Surface"),
    (b"PK\x03\x04", "ZIP/CryPak"),
    (b"\x1bLua", "Lua bytecode"),
    (b"\x1bLJ", "LuaJIT bytecode"),
    (b"AKPK", "Wwise file package"),
    (b"BKHD", "Wwise SoundBank"),
    (b"RIFF", "RIFF container"),
    (b"FSB5", "FMOD sound bank"),
    (b"CCCC", "CryEngine binary XML"),
    (b"<?xml", "XML (text)"),
    (b"MZ", "PE executable/DLL"),
]


def identify(head: bytes) -> str | None:
    for magic, label in MAGICS:
        if head.startswith(magic):
            return label
    return None


class Registry:
    """Install-wide, deduplicated store of header signatures and chunk variants.

    A 41 GB install repeats the same few hundred header shapes across tens of
    archives. Recording each occurrence would make the report grow with the
    install; recording each *distinct* shape keeps it flat, and loses nothing,
    because a second identical header teaches us nothing the first did not.
    """

    def __init__(self, examples_per_signature: int = 3):
        self.examples_per_signature = examples_per_signature
        self.signatures: dict[str, dict[str, Any]] = {}
        self.chunk_variants: dict[str, dict[str, Any]] = {}

    def add_sample(self, name: str, ext: str, size: int, head: bytes) -> None:
        key = binascii.hexlify(head[:SIGNATURE_KEY_BYTES]).decode()
        record = self.signatures.get(key)
        if record is None:
            record = {
                "key_hex": key,
                "head_hex": binascii.hexlify(head).decode(),
                "identified": identify(head),
                "extensions": {},
                "count": 0,
                "examples": [],
            }
            self.signatures[key] = record
        record["count"] += 1
        record["extensions"][ext] = record["extensions"].get(ext, 0) + 1
        if len(record["examples"]) < self.examples_per_signature:
            record["examples"].append({"name": name, "size": size})

    def add_chunk(self, chunk: dict[str, Any], name: str, ext: str) -> None:
        key = "|".join(
            f"{k}={chunk[k]}"
            for k in ("header", "file_type", "version")
            if k in chunk
        )
        record = self.chunk_variants.get(key)
        if record is None:
            record = dict(chunk)
            record["count"] = 0
            record["extensions"] = {}
            record["examples"] = []
            # Per-file offsets vary and say nothing about the format variant.
            record.pop("chunk_table_offset", None)
            record.pop("chunk_count", None)
            self.chunk_variants[key] = record
        record["count"] += 1
        record["extensions"][ext] = record["extensions"].get(ext, 0) + 1
        if len(record["examples"]) < self.examples_per_signature:
            record["examples"].append(name)

    def as_report(self) -> dict[str, Any]:
        return {
            "signatures": sorted(
                self.signatures.values(), key=lambda r: -r["count"]
            ),
            "chunk_variants": sorted(
                self.chunk_variants.values(), key=lambda r: -r["count"]
            ),
        }


def _rel(path: str, root: str) -> str:
    """Relative, forward-slashed path. Never absolute — that would leak a username."""
    return os.path.relpath(path, root).replace(os.sep, "/")


def find_archives(root: str) -> list[str]:
    found = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if name.lower().endswith(".pak"):
                found.append(os.path.join(dirpath, name))
    return sorted(found)


def survey_binaries(root: str) -> dict[str, Any]:
    """Catalog executables and libraries, and infer the audio middleware."""
    binaries = []
    middleware: set[str] = set()
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            lower = name.lower()
            if not lower.endswith((".exe", ".dll", ".so", ".dylib")):
                continue
            full = os.path.join(dirpath, name)
            try:
                size = os.path.getsize(full)
            except OSError:
                size = -1
            binaries.append({"path": _rel(full, root), "size": size})

            stem = os.path.splitext(lower)[0]
            for hint, label in AUDIO_IMPL_HINTS.items():
                # Match a real name boundary, so "ak" does not fire on "bake".
                if stem == hint or stem.startswith(hint):
                    middleware.add(label)

    binaries.sort(key=lambda b: b["path"])
    return {
        "count": len(binaries),
        "audio_middleware_detected": sorted(middleware) or ["UNDETERMINED"],
        "files": binaries[:400],
        "truncated": len(binaries) > 400,
    }


def parse_chunk_header(head: bytes) -> dict[str, Any] | None:
    """Read a CryEngine chunked-file header, if this looks like one.

    Two layouts exist. The legacy one opens with ``CryTek\\0\\0`` then file
    type, version and chunk-table offset; the newer one opens with ``CrCh``
    then version, chunk count and table offset. Both are recorded raw — the
    version numbers are the interesting part, because that is where Arkane's
    fork will show up against stock CryEngine.
    """
    try:
        if head.startswith(b"CryTek\x00\x00") and len(head) >= 20:
            file_type, version, table_offset = struct.unpack_from("<III", head, 8)
            return {
                "header": "legacy",
                "file_type": file_type,
                "version": version,
                "chunk_table_offset": table_offset,
            }
        if head.startswith(b"CrCh") and len(head) >= 16:
            version, chunk_count, table_offset = struct.unpack_from("<III", head, 4)
            return {
                "header": "CrCh",
                "version": version,
                "chunk_count": chunk_count,
                "chunk_table_offset": table_offset,
            }
    except struct.error:
        return None
    return None


def survey_archive(
    path: str, root: str, samples_per_ext: int, registry: Registry
) -> dict[str, Any]:
    """Summarize one archive: histograms plus a few header samples per type."""
    record: dict[str, Any] = {
        "path": _rel(path, root),
        "size": os.path.getsize(path),
    }

    try:
        pak = paktool.Pak(path)
    except (paktool.PakError, OSError) as exc:
        record["error"] = str(exc)
        record["readable_as_zip"] = False
        return record

    with pak:
        files = [e for e in pak.entries if not e.is_dir]
        record["readable_as_zip"] = True
        record["entries"] = len(files)
        record["declared_entries"] = pak.declared_count
        record["offset_delta"] = pak.offset_delta
        record["uncompressed_size"] = sum(e.uncomp_size for e in files)
        record["compressed_size"] = sum(e.comp_size for e in files)

        methods = collections.Counter(e.method_name for e in files)
        record["methods"] = dict(methods)
        record["unreadable_entries"] = sum(1 for e in files if not e.readable)

        exts = collections.Counter(e.ext for e in files)
        record["extensions"] = dict(exts.most_common())

        # Sample a few headers per extension. This is where format evidence
        # comes from, and it is why the report is worth more than a listing.
        # Results go to the install-wide registry, which collapses duplicates.
        sampled = errors = 0
        taken: collections.Counter[str] = collections.Counter()

        for entry in files:
            if taken[entry.ext] >= samples_per_ext:
                continue
            if not entry.readable or entry.uncomp_size == 0:
                continue
            try:
                head = pak.read(entry)[:HEADER_BYTES]
            except Exception:  # noqa: BLE001 - one bad entry must not stop the survey
                errors += 1
                taken[entry.ext] += 1
                continue

            taken[entry.ext] += 1
            sampled += 1
            registry.add_sample(entry.name, entry.ext, entry.uncomp_size, head)

            chunk = parse_chunk_header(head)
            if chunk:
                registry.add_chunk(chunk, entry.name, entry.ext)

        record["sampled"] = sampled
        record["sample_errors"] = errors

        # Lua ships either as text or as bytecode, and bytecode would be
        # version- and endianness-bound -- which matters on ARM64.
        lua = [e for e in files if e.ext == ".lua" and e.readable]
        if lua:
            source = bytecode = unknown = 0
            for entry in lua[:200]:
                try:
                    head = pak.read(entry)[:4]
                except Exception:  # noqa: BLE001
                    unknown += 1
                    continue
                if head.startswith((b"\x1bLua", b"\x1bLJ")):
                    bytecode += 1
                elif head:
                    source += 1
                else:
                    unknown += 1
            record["lua"] = {
                "sampled": min(len(lua), 200),
                "total": len(lua),
                "source": source,
                "bytecode": bytecode,
                "unknown": unknown,
            }

    return record


def aggregate(archives: list[dict[str, Any]]) -> dict[str, Any]:
    exts: collections.Counter[str] = collections.Counter()
    methods: collections.Counter[str] = collections.Counter()
    total_u = total_c = 0
    unreadable = 0

    for a in archives:
        if not a.get("readable_as_zip"):
            continue
        exts.update(a.get("extensions", {}))
        methods.update(a.get("methods", {}))
        total_u += a.get("uncompressed_size", 0)
        total_c += a.get("compressed_size", 0)
        unreadable += a.get("unreadable_entries", 0)

    return {
        "archives": len(archives),
        "archives_unreadable": sum(1 for a in archives if not a.get("readable_as_zip")),
        "total_entries": sum(a.get("entries", 0) for a in archives),
        "entries_needing_crypak_decoding": unreadable,
        "uncompressed_size": total_u,
        "compressed_size": total_c,
        "extensions": dict(exts.most_common()),
        "methods": dict(methods.most_common()),
    }


def write_listing(archives_on_disk: list[str], root: str, dest: str) -> int:
    """Write every entry name across all archives, gzipped. Opt-in: it is large."""
    written = 0
    with gzip.open(dest, "wt", encoding="utf-8") as out:
        for path in archives_on_disk:
            try:
                pak = paktool.Pak(path)
            except (paktool.PakError, OSError):
                continue
            with pak:
                prefix = _rel(path, root)
                for entry in pak.entries:
                    if entry.is_dir:
                        continue
                    out.write(f"{prefix}\t{entry.uncomp_size}\t{entry.name}\n")
                    written += 1
    return written


def digest(report: dict[str, Any], top_ext: int = 30, top_sig: int = 60) -> str:
    """Render the report as a dense text block small enough to paste in chat.

    The full JSON can reach a few megabytes on a real install, which is awkward
    to move from a phone. Almost all of its value, though, is in a few hundred
    lines: the histograms, the distinct header signatures, and the chunk
    variants. This is that, and nothing else -- typically a handful of KB.
    """
    totals = report["totals"]
    binaries = report["binaries"]
    out: list[str] = []
    add = out.append

    add(f"PREY PROBE DIGEST v{report.get('probe_version', '?')}")
    add(f"install={report.get('install_name', '?')} "
        f"platform={report.get('platform', '?')} "
        f"archives={totals['archives']} "
        f"unreadable={totals['archives_unreadable']} "
        f"entries={totals['total_entries']}")
    add(f"uncompressed={_human(totals['uncompressed_size'])} "
        f"compressed={_human(totals['compressed_size'])}")
    add(f"audio={'; '.join(binaries['audio_middleware_detected'])} "
        f"binaries={binaries['count']}")
    add(f"crypak_only_entries={totals['entries_needing_crypak_decoding']}")

    lua = [a["lua"] for a in report["archives"] if "lua" in a]
    if lua:
        src = sum(l["source"] for l in lua)
        bc = sum(l["bytecode"] for l in lua)
        add(f"lua source={src} bytecode={bc}")

    add("")
    add("METHODS")
    for name, count in totals["methods"].items():
        flag = "" if name in ("store", "deflate") else "   <-- CryEngine codec"
        add(f"  {count:>8} {name}{flag}")

    add("")
    add(f"EXT (top {top_ext} of {len(totals['extensions'])})")
    for ext, count in list(totals["extensions"].items())[:top_ext]:
        add(f"  {count:>8} {ext}")

    signatures = report.get("signatures", [])
    shown = signatures[:top_sig]
    add("")
    add(f"SIG (top {len(shown)} of {len(signatures)} distinct header signatures)")
    for sig in shown:
        exts = ",".join(sorted(sig["extensions"]))
        label = sig["identified"] or "UNRECOGNIZED"
        add(f"  {sig['count']:>8} {exts:<14} {sig['key_hex']}  {label}")
    if len(signatures) > top_sig:
        add(f"  ... {len(signatures) - top_sig} more (full set is in the JSON)")

    variants = report.get("chunk_variants", [])
    if variants:
        add("")
        add("CHUNK VARIANTS")
        for v in variants:
            bits = " ".join(
                f"{k}={v[k]}" for k in ("header", "version", "file_type") if k in v
            )
            exts = ",".join(sorted(v["extensions"]))
            add(f"  {v['count']:>8} {exts:<14} {bits}")

    # Never truncated: these are the formats nobody has identified yet, which
    # is precisely the part worth carrying back.
    unknown = [s for s in signatures if not s["identified"]]
    if unknown:
        add("")
        add(f"UNRECOGNIZED ({len(unknown)}, all listed) — format work queue")
        for sig in unknown:
            example = sig["examples"][0]["name"] if sig["examples"] else "?"
            add(f"  {sig['count']:>8} {sig['key_hex']}  {example}")

    add("")
    add("END DIGEST")
    return "\n".join(out)


def _human(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TiB"


def print_summary(report: dict[str, Any]) -> None:
    totals = report["totals"]
    binaries = report["binaries"]

    print("=" * 62)
    print("Prey install survey")
    print("=" * 62)
    print(f"archives found      {totals['archives']}"
          + (f"  ({totals['archives_unreadable']} unreadable)"
             if totals["archives_unreadable"] else ""))
    print(f"total entries       {totals['total_entries']}")
    print(f"uncompressed        {_human(totals['uncompressed_size'])}")
    print(f"compressed          {_human(totals['compressed_size'])}")
    print(f"binaries found      {binaries['count']}")
    print(f"audio middleware    {', '.join(binaries['audio_middleware_detected'])}")

    blocked = totals["entries_needing_crypak_decoding"]
    print(f"CryPak-only entries {blocked}"
          + ("  <-- custom codec work needed" if blocked else "  (none: plain ZIP suffices)"))

    print("\ncompression methods")
    for name, count in totals["methods"].items():
        mark = "" if name in ("store", "deflate") else "   <-- CryEngine codec"
        print(f"  {count:>9}  {name}{mark}")

    print("\ntop extensions")
    for ext, count in list(totals["extensions"].items())[:20]:
        print(f"  {count:>9}  {ext}")

    identified: dict[str, int] = {}
    unknown = 0
    for sig in report.get("signatures", []):
        if sig["identified"]:
            identified[sig["identified"]] = (
                identified.get(sig["identified"], 0) + sig["count"]
            )
        else:
            unknown += 1
    if identified:
        print("\nidentified header formats (deduplicated)")
        for label, count in sorted(identified.items(), key=lambda kv: -kv[1]):
            print(f"  {count:>9}  {label}")
    if unknown:
        print(f"\n{unknown} distinct header signature(s) not recognized"
              "  <-- candidates for format work")

    print(f"\ndistinct signatures   {len(report.get('signatures', []))}")
    print(f"distinct chunk types  {len(report.get('chunk_variants', []))}")
    for variant in report.get("chunk_variants", []):
        bits = [f"{k}={variant[k]}" for k in ("header", "version") if k in variant]
        print(f"  {variant['count']:>9}  {' '.join(bits)}")

    print("\n" + "=" * 62)
    print(f"Report written to: {report['_output']}")
    print("Commit that file, or paste it back. It contains no asset data.")
    print("=" * 62)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="probe",
        description="Survey a Prey install and emit a small, shareable metadata report.",
    )
    parser.add_argument("install", help="path to the Prey install directory")
    parser.add_argument("-o", "--output", default="prey-report.json")
    parser.add_argument(
        "--samples", type=int, default=3,
        help="header samples per file extension per archive (default 3)",
    )
    parser.add_argument(
        "--listing", metavar="FILE.txt.gz",
        help="also write every entry name to a gzipped listing (large; opt-in)",
    )
    parser.add_argument(
        "--digest", nargs="?", const="-", metavar="FILE",
        help="also write a paste-sized text digest (default: stdout)",
    )
    args = parser.parse_args(argv)

    root = os.path.abspath(args.install)
    if not os.path.isdir(root):
        print(f"probe: not a directory: {args.install}", file=sys.stderr)
        return 2

    print(f"scanning {root} ...", file=sys.stderr)
    archives_on_disk = find_archives(root)
    print(f"found {len(archives_on_disk)} archive(s)", file=sys.stderr)

    registry = Registry()
    archives = []
    for i, path in enumerate(archives_on_disk, 1):
        print(f"  [{i}/{len(archives_on_disk)}] {_rel(path, root)}", file=sys.stderr)
        archives.append(survey_archive(path, root, args.samples, registry))

    report: dict[str, Any] = {
        "probe_version": PROBE_VERSION,
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "platform": platform.system(),
        "install_name": os.path.basename(root),  # basename only, never the full path
        "binaries": survey_binaries(root),
        "archives": archives,
        "totals": aggregate(archives),
        **registry.as_report(),
    }

    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=False)

    if args.listing:
        count = write_listing(archives_on_disk, root, args.listing)
        print(f"listing: {count} entries -> {args.listing}", file=sys.stderr)

    if args.digest:
        text = digest(report)
        if args.digest == "-":
            print(text)
        else:
            with open(args.digest, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
            print(f"digest: {len(text)} chars -> {args.digest}", file=sys.stderr)

    report["_output"] = args.output
    print_summary(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
