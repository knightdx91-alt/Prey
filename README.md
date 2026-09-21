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
| `docs/` | Architecture, format notes, roadmap |
| `tools/paktool/` | CryPak (`.pak`) inspection and extraction |

## Requirements

- Python 3.9+ for the tooling in `tools/`
- Your own legally acquired copy of Prey. **No game data is distributed here.**

## Quick start

Point the pak tool at a game install and see what is inside:

```sh
python3 tools/paktool/paktool.py list  "/path/to/Prey/GameSDK/GameData.pak"
python3 tools/paktool/paktool.py stats "/path/to/Prey/GameSDK/GameData.pak"
python3 tools/paktool/paktool.py extract "/path/to/Prey/GameSDK/GameData.pak" -o out/
```

## Workflow

`main` only. No branches. No pull requests. See [`CLAUDE.md`](CLAUDE.md).

## Legal

Reverse engineering here is done under permission held by the repository owner.
Prey, Arkane, and Bethesda are trademarks of their respective owners; this
project is unaffiliated with and unendorsed by either. No copyrighted game
assets are redistributed.
