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
- [x] `budget` — Android footprint model (`docs/SIZE_BUDGET.md`)
- [x] `device` — target capability probe (`docs/DEVICE.md`)

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

**Viable — confirmed.** Reference device is a Galaxy Z Fold 8, `SM-F971U`:
SoC `SM8850` with `ro.hardware.egl = adreno`, so Snapdragon and Adreno, so
Turnip applies. See `docs/DEVICE.md`.

- [x] Confirm the GPU family — **Adreno 840**, measured
- [x] Vulkan version — **1.4.295**, Qualcomm driver 512.842.19
- [x] Texture format support — **BC, ASTC LDR+HDR and ETC2 all supported**
- [ ] Box64/FEX + Wine + DXVK + Turnip bring-up (Adreno path)
- [ ] Get to a main menu; record everything that breaks getting there
- [ ] Capture reference frames for the native renderer to diff against
- [ ] Profile honestly and publish the numbers, however bad they are —
      over a sustained run, since a foldable throttles sooner than a slab

Exit criterion: a frame of Prey rendered on Android hardware, by any means, with
a capture to compare against later.

## Phase 3 — Asset pipeline

Desktop install is ~41 GB. The model in `docs/SIZE_BUDGET.md` puts a balanced
mobile build near 9.5 GB, and names geometry — not textures — as the largest
remaining category, because texture compression has a well-understood mobile
answer and mesh data does not.

- [ ] Decide the conversion strategy: on-device needs ~50 GB peak (41 GB source
      alongside its output) against 26.64 GB free. Incremental conversion —
      releasing each source archive as its output lands — keeps the peak near
      `output + largest archive` instead
- [ ] Mesh optimization and vertex stream repacking **(largest category after
      reduction; start here, against instinct)**
- [ ] LOD policy — decide what a phone actually needs
- [ ] **Optional now:** BC → ASTC transcoding. The GPU samples BC directly, so
      a first build needs only mip dropping. Schedule this for size, not to
      unblock anything
- [ ] Locale policy; audio re-encoding
- [ ] Video re-encode or cut
- [ ] Android asset packaging; confirm current Play delivery limits, which
      `budget.py` currently carries as UNVERIFIED
- [ ] Feed measured ratios back into `budget.py`

Exit criterion: the full game's data, converted, with a measured install size
to replace the model's estimate.

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
