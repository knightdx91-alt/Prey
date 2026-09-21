# Roadmap

Sequenced by what unblocks the most, not by what is most exciting. Everything
before "runtime" is cheap and gives real answers; the runtime work is neither,
so it should not start until the data model is pinned down.

## Phase 0 — Repository foundations ✅

- [x] Workflow law (`main` only, no branches, no PRs)
- [x] Porting strategy written down (`docs/ARCHITECTURE.md`)
- [x] Format hypotheses recorded with confidence markers
- [x] Git LFS configured for large binaries
- [x] `paktool` — CryPak inspection and extraction

## Phase 1 — Data archaeology

The goal of this phase is to replace every **UNVERIFIED** in
`docs/ASSET_FORMATS.md` with something traceable to bytes.

- [ ] Run `paktool stats` against a real install; record the archive inventory
- [ ] Confirm whether standard ZIP parsing suffices, and catalog what it misses
- [ ] Extension histogram across all archives — establishes what actually ships
- [ ] `.cgf`/`.chr` chunk table parser; record chunk types and versions
- [ ] `.dds` inspection, including the split-mip companion files
- [ ] Identify the audio middleware from the shipped binaries
- [ ] Determine whether Lua ships as source or bytecode

Exit criterion: a documented, parseable path from a game install to geometry,
textures, and materials in a form a renderer could consume.

## Phase 2 — Reference runtime (the oracle)

- [ ] Box64/FEX + Wine + DXVK + Turnip bring-up on an Adreno device
- [ ] Get to a main menu; record everything that breaks getting there
- [ ] Capture reference frames for the native renderer to diff against
- [ ] Profile honestly and publish the numbers, however bad they are

Exit criterion: a frame of Prey rendered on Android hardware, by any means, with
a capture to compare against later.

## Phase 3 — Asset pipeline

- [ ] BC → ASTC transcoding
- [ ] Mesh optimization and vertex stream repacking for mobile bandwidth
- [ ] Audio re-encoding
- [ ] Android asset packaging, sized against Play delivery limits

Exit criterion: the full game's data, converted, with a measured install size.

## Phase 4 — Native runtime

- [ ] Android app shell, Gradle + NDK, ARM64
- [ ] Vulkan device/swapchain bring-up
- [ ] Resource system reading Phase 3 output
- [ ] Static geometry and materials on screen
- [ ] Skinned characters and animation
- [ ] Lua VM and the game systems it drives
- [ ] Physics
- [ ] Audio
- [ ] Touch and gamepad input

No exit criterion written yet. This phase is where the multi-year estimate
lives, and dates set before Phase 1 finishes would be invented.

## Not doing

- Distributing game assets. Ever. Tooling reads from the user's own install.
- Online or multiplayer anything — Prey is single-player.
- Non-ARM64 Android targets.
