#!/usr/bin/env python3
"""budget — model Prey's Android install footprint.

Prey Digital Deluxe is roughly 41 GB on desktop. No Android delivery channel
takes that, so the question is not whether the data shrinks but by how much,
and whether what is left fits anything.

This models it. Desktop assets are sized for a GPU with dedicated VRAM and a
mechanical budget nobody was counting; mobile needs different texture formats,
lower resolutions, fewer locales, and cheaper audio. Each of those is a known
multiplier, so the footprint can be estimated before a single byte is converted.

Run it against a probe report for real category sizes, or against a headline
total with assumed proportions when no report exists yet:

    budget.py --total-gb 41
    budget.py --report prey-report.json --profile aggressive

Every factor here is an ESTIMATE until measured against real conversions. The
point is a defensible starting number and an explicit place to correct it.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

# Extension -> category. Split-mip companions (.dds.1, .dds.2) surface as
# numeric extensions, so those count as texture data too.
CATEGORIES: dict[str, tuple[str, ...]] = {
    "texture": (".dds", ".tif", ".tiff", ".tga", ".png", ".jpg", ".bmp",
                ".1", ".2", ".3", ".4", ".5", ".6", ".7", ".8", ".9"),
    "audio": (".bnk", ".pck", ".wem", ".ogg", ".wav", ".mp3", ".fsb", ".akd"),
    "video": (".bk2", ".usm", ".webm", ".mp4", ".avi", ".sfd", ".mkv"),
    "geometry": (".cgf", ".cga", ".chr", ".skin", ".caf", ".anm", ".cdf", ".cid"),
    "script": (".lua", ".xml", ".txt", ".json", ".cfg", ".ini", ".csv", ".cfx", ".cfi"),
}

# Proportions for a modern AAA title, used only when no probe report is given.
# Rough, and the first thing a real report should replace.
ASSUMED_SPLIT: dict[str, float] = {
    "texture": 0.55,
    "audio": 0.20,
    "geometry": 0.12,
    "video": 0.08,
    "script": 0.02,
    "other": 0.03,
}

# Reduction factors per category. Reasoning is recorded alongside each, because
# a number without its derivation cannot be argued with or corrected.
#
# The target GPU (Adreno 840) supports BC, ASTC and ETC2 -- measured, see
# docs/DEVICE.md. That makes BC->ASTC transcoding an optimization rather than a
# requirement, which is what the "passthrough" profile exists to price.
PROFILES: dict[str, dict[str, Any]] = {
    "passthrough": {
        "description": "Keep desktop BC textures as-is; only drop resolution. "
                       "No transcoder needed -- the fastest route to a build.",
        "factors": {
            # MEASURED on Adreno 840: textureCompressionBC is supported, so
            # Prey's shipped BC1/BC3/BC5/BC7 textures can be sampled directly.
            # Halving each dimension quarters the pixel count; bits-per-pixel
            # is unchanged because the format is unchanged.
            "texture": 0.25,
            "audio": 0.18,
            "video": 0.20,
            "geometry": 0.60,
            "script": 1.0,
            "other": 0.90,
        },
    },
    "quality": {
        "description": "Keep visual fidelity high; accept a large install.",
        "factors": {
            # BC7 (8 bpp) -> ASTC 6x6 (3.56 bpp) at full resolution.
            "texture": 3.56 / 8,
            # Drop non-English voice, keep music and effects at current rates.
            "audio": 0.45,
            # Re-encode cinematics to HEVC at 1080p.
            "video": 0.35,
            # Vertex quantization; LODs retained.
            "geometry": 0.80,
            "script": 1.0,
            "other": 1.0,
        },
    },
    "balanced": {
        "description": "Target a phone that exists today. The default.",
        "factors": {
            # ASTC 6x6 at half resolution: (3.56/8) x (1/4 the pixels).
            "texture": (3.56 / 8) * 0.25,
            # English only, Opus at a mobile-appropriate bitrate.
            "audio": 0.18,
            # HEVC at 720p.
            "video": 0.20,
            # Vertex quantization plus dropping the highest LOD.
            "geometry": 0.60,
            "script": 1.0,
            "other": 0.90,
        },
    },
    "aggressive": {
        "description": "Smallest plausible build; visible quality cost.",
        "factors": {
            # ASTC 8x8 (2 bpp) at half resolution.
            "texture": (2.0 / 8) * 0.25,
            # English only, lower bitrate, shorter tails.
            "audio": 0.12,
            # HEVC at 540p, or cut cinematics entirely.
            "video": 0.10,
            "geometry": 0.45,
            "script": 1.0,
            "other": 0.80,
        },
    },
}

# Android delivery ceilings. UNVERIFIED -- confirm against current Play policy
# before planning around them; they move, and they differ by delivery mode.
DELIVERY_TARGETS: list[tuple[str, float]] = [
    ("Play base module (download)", 0.2),
    ("Play Asset Delivery, install-time", 1.0),
    ("Play, total app size", 4.0),
    ("Sideload / OBB-style install", 100.0),
]

GB = 1024 ** 3


def categorize(ext: str) -> str:
    lowered = ext.lower()
    for category, extensions in CATEGORIES.items():
        if lowered in extensions:
            return category
    return "other"


def sizes_from_report(report: dict[str, Any]) -> dict[str, int]:
    """Per-category byte totals from a probe report.

    The probe records an extension histogram (counts) and per-archive totals,
    but not bytes per extension -- so this apportions each archive's
    uncompressed total across its extensions by entry count. Coarse, and
    better than an assumed split, since it is at least this install's mix.
    """
    totals: dict[str, float] = {}
    for archive in report.get("archives", []):
        if not archive.get("readable_as_zip"):
            continue
        exts = archive.get("extensions", {})
        entries = sum(exts.values())
        if not entries:
            continue
        archive_bytes = archive.get("uncompressed_size", 0)
        for ext, count in exts.items():
            share = archive_bytes * (count / entries)
            totals[categorize(ext)] = totals.get(categorize(ext), 0.0) + share
    return {k: int(v) for k, v in totals.items()}


def sizes_from_total(total_bytes: int) -> dict[str, int]:
    return {k: int(total_bytes * share) for k, share in ASSUMED_SPLIT.items()}


def model(sizes: dict[str, int], profile: str) -> dict[str, Any]:
    factors = PROFILES[profile]["factors"]
    rows = []
    before = after = 0
    for category in sorted(sizes, key=lambda c: -sizes[c]):
        original = sizes[category]
        factor = factors.get(category, 1.0)
        reduced = int(original * factor)
        rows.append({
            "category": category,
            "original": original,
            "factor": factor,
            "reduced": reduced,
        })
        before += original
        after += reduced
    return {
        "profile": profile,
        "rows": rows,
        "total_before": before,
        "total_after": after,
        "ratio": (before / after) if after else 0.0,
    }


def _size(n: float) -> str:
    """Adaptive units, so a small survey does not render as a column of 0.00 GB."""
    for unit, scale in (("GB", GB), ("MB", 1024 ** 2), ("KB", 1024)):
        if n >= scale:
            return f"{n / scale:.2f} {unit}"
    return f"{n:.0f} B"


def render(result: dict[str, Any], source: str) -> None:
    profile = result["profile"]
    print("=" * 66)
    print(f"Android footprint estimate — profile: {profile}")
    print(f"  {PROFILES[profile]['description']}")
    print(f"  source: {source}")
    print("=" * 66)
    print(f"{'category':<12}{'desktop':>12}{'factor':>10}{'android':>12}")
    print("-" * 66)
    for row in result["rows"]:
        print(f"{row['category']:<12}{_size(row['original']):>12}"
              f"{row['factor']:>10.3f}{_size(row['reduced']):>12}")
    print("-" * 66)
    print(f"{'TOTAL':<12}{_size(result['total_before']):>12}"
          f"{'':>10}{_size(result['total_after']):>12}")
    print(f"\nreduction: {result['ratio']:.1f}x")

    after_gb = result["total_after"] / GB
    print("\nagainst delivery ceilings (UNVERIFIED — confirm against Play policy)")
    for label, limit in DELIVERY_TARGETS:
        verdict = "fits" if after_gb <= limit else f"over by {after_gb - limit:.1f} GB"
        print(f"  {label:<38} {limit:>6.1f} GB   {verdict}")

    print("\nEvery factor above is an estimate. Replace them with measurements")
    print("from real conversions as soon as the asset pipeline exists.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="budget",
        description="Estimate Prey's Android install footprint.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--report", help="probe report JSON")
    source.add_argument("--total-gb", type=float, help="headline install size in GB")
    parser.add_argument(
        "--profile", choices=sorted(PROFILES), default="balanced",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead")
    parser.add_argument(
        "--all-profiles", action="store_true", help="compare every profile",
    )
    args = parser.parse_args(argv)

    if args.report:
        try:
            with open(args.report, encoding="utf-8") as fh:
                report = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"budget: {exc}", file=sys.stderr)
            return 2
        sizes = sizes_from_report(report)
        source_label = f"probe report ({args.report})"
        if not sizes:
            print("budget: report contains no readable archives", file=sys.stderr)
            return 2
    else:
        sizes = sizes_from_total(int(args.total_gb * GB))
        source_label = f"assumed split of {args.total_gb:g} GB"

    profiles = sorted(PROFILES) if args.all_profiles else [args.profile]
    results = [model(sizes, p) for p in profiles]

    if args.json:
        json.dump(
            {"source": source_label, "results": results}, sys.stdout, indent=2
        )
        print()
        return 0

    for i, result in enumerate(results):
        if i:
            print()
        render(result, source_label)
    return 0


if __name__ == "__main__":
    sys.exit(main())
