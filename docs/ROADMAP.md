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

**First pass complete (2026-09-22).** Everything below was settled by one probe
run against the reference install. See `ASSET_FORMATS.md` for the evidence.

Settled:

- [x] Archive inventory — **116 archives, 264,336 entries, 0 unreadable**
- [x] Whether standard ZIP parsing suffices — **yes, entirely.** deflate and
      store only; zero entries need CryPak-aware decoding
- [x] Extension histogram — **69.9% of files are texture data**
- [x] `.cgf`/`.chr` chunk header — **`CrCh`, version 1862, one version
      across every geometry and animation type**
- [x] Audio middleware — **Wwise** (13,486 `.wem`, no `.bnk` banks)
- [x] Lua — **bytecode, 419 files, zero source**

Still open — all single-file reads now that extraction is known to work:

- [ ] **DDS pixel format.** The FourCC sits at offset 84, past the probe's
      64-byte sample window. Decides BC1/BC3/BC5/BC7
- [ ] `.mtl` encoding — text XML or CryEngine binary XML
- [ ] Lua bytecode variant — which Lua or LuaJIT build
- [ ] `.cgf` chunk *table* contents (header and offset are known)
- [ ] `.wem` codec, for the audio re-encode stage
- [x] ~~CryPak custom codecs~~ — **none exist.** Nothing to do

Exit criterion: a documented, parseable path from a game install to geometry,
textures, and materials in a form a renderer could consume.

## Phase 2 — Translation layer (now the primary path, not just an oracle)

**Do the cheap experiment first.** Install a Winlator-class environment and try
to launch Prey. That one test bounds the whole project's ceiling and produces a
work list of whatever fails. See `FEASIBILITY.md`, and `PHASE2_SETUP.md` for
which build to try and why the graphics driver matters more than the wrapper.


**Viable — confirmed.** Reference device is a Galaxy Z Fold 8, `SM-F971U`:
SoC `SM8850` with `ro.hardware.egl = adreno`, so Snapdragon and Adreno, so
Turnip applies. See `docs/DEVICE.md`.

- [x] Confirm the GPU family — **Adreno 840**, measured
- [x] Vulkan version — **1.4.295**, Qualcomm driver 512.842.19
- [x] Texture format support — **BC, ASTC LDR+HDR and ETC2 all supported**
- [ ] Establish whether current Turnip supports Adreno 840 — the gating
      unknown, since driver maturity for new silicon lags the hardware
- [x] Box64/FEX + Wine + DXVK bring-up — **done; the game renders 3D
      gameplay on device**
- [x] Get to a main menu — **passed; reached early gameplay**
- [ ] Diagnose the early-suit-sequence crash (see `PHASE2_LOG.md`)
- [ ] Establish whether crashes are deterministic or memory-driven —
      **one clean retry moved the hypothesis toward memory;** accumulate 4-5
      crash records to confirm
- [ ] Test whether Prey honours `r_TexturesStreamPoolSize` as a stopgap
- [ ] Capture reference frames for the native renderer to diff against
- [ ] Profile honestly and publish the numbers, however bad they are —
      over a sustained run, since a foldable throttles sooner than a slab

Exit criterion: a frame of Prey rendered on Android hardware, by any means, with
a capture to compare against later.

## Phase 3 — Asset pipeline

**May be the stability fix, not just a size fix.** If the Phase 2 crashes are
memory-driven, lower-resolution textures cut the streaming footprint directly
and this phase moves earlier in priority. See `PHASE2_LOG.md`.

Desktop install is 29.3 GiB on disk, 59.5 GiB uncompressed. The model in `docs/SIZE_BUDGET.md` puts a balanced
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

## Phase 3.5 — Bundled-stack APK

The actual deliverable. **Gated on Phase 2** — there is no point packaging a
configuration that has not been shown to run.

### What the APK actually contains

Not the game. 29.3 GiB of game data cannot live inside an APK: Play caps the
base module in the hundreds of megabytes, and even a sideloaded APK is the
wrong container for tens of gigabytes.

The realistic architecture is a **launcher plus runtime**:

| Component | Where it lives | Size |
|---|---|---|
| Wine prefix, Box64, DXVK, driver | inside the APK | ~1–2 GB |
| Launcher that boots straight into the game | inside the APK | trivial |
| Game data | external storage, placed once | 29.3 GiB |

That is the same shape emulator frontends and console-style installs use, and
it still delivers the thing that matters: tap an icon, the game starts, no
container UI, no drive mapping, no Wine desktop.

An installer flow inside the app can handle placing the data, so the user
experience is "install app, point it at the game files once, play."

- [ ] Reach a playable configuration in Winlator first (Phases 2–3)
- [ ] Capture that container configuration reproducibly
- [ ] Build an APK shipping the runtime preconfigured
- [ ] Launcher that skips the container UI entirely
- [ ] First-run flow for locating or importing the game data
- [ ] Bundle the converted assets from Phase 3 where size allows

Exit criterion: an installable app that launches Prey without the user
touching a container setting.

## Phase 4 — Native runtime (OUT OF SCOPE)

> **See `docs/FEASIBILITY.md`.** This phase is not a port. Prey runs on
> Arkane's fork of CryEngine, so a native runtime means writing a Vulkan
> renderer matching a modified engine, plus physics, animation, audio and
> scripting — and then reimplementing Prey's game systems on top, from a
> stripped binary with no decompilation to build on. Comparable projects
> (devilutionX, OpenMW, Ship of Harkinian) targeted older, smaller games and
> each had a decompilation or an open engine to start from. None of that
> exists here.
>
> Kept below as a record of what it would entail, not as a plan.

### Original scope, retained for reference

- [ ] Android app shell, Gradle + NDK, ARM64
- [ ] Vulkan device/swapchain bring-up
- [ ] Resource system reading Phase 3 output
- [ ] Static geometry and materials on screen
- [ ] Skinned characters and animation
- [ ] Lua VM and the game systems it drives
- [ ] Physics
- [ ] Audio
- [ ] Touch and gamepad input

No exit criterion, because there is no realistic solo path to one. The
achievable goal is the translation layer plus the asset pipeline — see
`FEASIBILITY.md` for the reframe.

## Not doing

- Distributing game assets. Ever. Tooling reads from the user's own install.
- Online or multiplayer anything — Prey is single-player.
- Non-ARM64 Android targets.
