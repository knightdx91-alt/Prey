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
- [x] `probe` — whole-install survey, so findings travel without the assets
- [x] Data-sharing workflow documented (`docs/GETTING_DATA.md`)

## Phase 1 — Data archaeology

The goal of this phase is to replace every **UNVERIFIED** in
`docs/ASSET_FORMATS.md` with something traceable to bytes.

**Blocked on one probe run.** The game data stays on the owner's machine; the
survey is what crosses. See `GETTING_DATA.md`.

Settled by the first `probe` run:

- [ ] Archive inventory across the whole install
- [ ] Whether standard ZIP parsing suffices, and exactly what it misses
- [ ] Extension histogram — what actually ships, versus what docs imply
- [ ] `.cgf`/`.chr` chunk header layout and version numbers
- [ ] Audio middleware, from the ATL implementation DLL
- [ ] Lua as source or bytecode

Needs work beyond the probe:

- [ ] Full `.cgf` chunk *table* parser (the probe reads only the file header)
- [ ] `.dds` inspection, including the split-mip companion files
- [ ] `.mtl` parsing, including CryEngine binary XML if that is what ships
- [ ] CryPak custom codecs, for whatever the probe flags as undecodable

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
