# Prey → Android

An effort to run **Prey** (Arkane Studios Austin / Bethesda, 2017) on Android.

> **Status: bootstrap.** Nothing runs yet. The repository currently holds the
> workflow rules, the porting strategy, and the beginnings of the data-format
> tooling. See [`docs/ROADMAP.md`](docs/ROADMAP.md) for what lands next.

## What this is

Prey ships as an x86-64 Windows binary on a heavily modified CryEngine, drawing
through Direct3D 11. Android gives us ARM64 and Vulkan. Every subsystem in
between has to be translated, reimplemented, or emulated, and the right answer
differs per subsystem.

This repo takes the position that the work splits cleanly in two, and that the
data side comes first:

**Track 1 — data archaeology.** Understand and unpack the shipped data:
archives, geometry, textures, materials, levels, audio banks, Lua. This is
tractable, testable, and required no matter which runtime strategy wins. It is
where the repo starts.

**Track 2 — runtime.** Get something drawing on a phone. Two candidate paths,
pursued in parallel rather than argued about in the abstract:

- *Translation layer* — Box64/FEX + Wine + DXVK on top of Vulkan (Turnip on
  Adreno). Fastest route to a frame on screen; likely unplayable performance,
  but it validates the data path and produces a reference renderer to diff
  against.
- *Native runtime* — an ARM64 host app with a Vulkan renderer that consumes the
  extracted data directly. Enormously more work; the only path to a version
  that is actually playable.

The translation layer is a measuring instrument. The native runtime is the
product.

## Layout

| Path | What lives there |
|---|---|
| `docs/` | Architecture, format notes, roadmap, data workflow |
| `tools/probe/` | Whole-install survey — the report you share |
| `tools/paktool/` | CryPak (`.pak`) inspection and extraction |
| `tools/budget/` | Android footprint model |

## Requirements

- Python 3.9+ for the tooling in `tools/`
- Your own legally acquired copy of Prey. **No game data is distributed here.**

## How the data works

**The game files stay on your machine.** They are not in this repo and cannot
be — a storefront login is required to download Prey, an agent has no business
holding your credentials, and a 20+ GB install does not belong in Git.

It turns out not to matter much. Nearly every open format question is
answerable from *metadata* measured in kilobytes. So the loop is: you run a
read-only survey locally, share the small report it produces, and the findings
and parsers improve from there.

**[`docs/TRANSFER.md`](docs/TRANSFER.md) is the step-by-step version**, including
running everything on an Android phone via Termux. See
[`docs/GETTING_DATA.md`](docs/GETTING_DATA.md) for the rationale behind it.

The install is ~41 GB, which matters for the *port* rather than for this
workflow. [`docs/SIZE_BUDGET.md`](docs/SIZE_BUDGET.md) works that arithmetic
out: roughly 9.5 GB on balanced settings, with geometry — not textures —
turning out to be the largest remaining category.

## Quick start

Survey your install — one command, no dependencies, nothing written to it:

```sh
python3 tools/probe/probe.py "/path/to/Prey" -o prey-report.json --digest digest.txt
```

`digest.txt` is the thing to share — a dense text block, usually under 20 KB,
small enough to paste straight into a chat. It holds counts, histograms,
64-byte header signatures and a list of formats nothing recognized yet. No
asset content, and no absolute paths.

To look inside a specific archive:

```sh
python3 tools/paktool/paktool.py stats "/path/to/Prey/GameSDK/GameData.pak"
python3 tools/paktool/paktool.py list  "$PAK" -l -p '*.cgf'
python3 tools/paktool/paktool.py extract "$PAK" -o out/ -p 'Materials/*'
```

## Tests

```sh
for t in paktool probe budget; do python3 -m unittest discover -s "tools/$t" -v; done
```

Fixtures are generated at runtime; no game data is required to run them.

## Workflow

`main` only. No branches. No pull requests. See [`CLAUDE.md`](CLAUDE.md).

## Legal

Reverse engineering here is done under permission held by the repository owner.
Prey, Arkane, and Bethesda are trademarks of their respective owners; this
project is unaffiliated with and unendorsed by either. No copyrighted game
assets are redistributed.
