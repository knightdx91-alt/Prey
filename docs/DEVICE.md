# Reference device

All work happens on a **Samsung Galaxy Z Fold 8, model `SM-F971U`**. That makes
it both the development machine and the target, so its capabilities are project
inputs rather than trivia.

## What this document does not do

It does not list the Fold 8's specifications. Hardware details for a device
this recent are outside what can be stated reliably here, and a confidently
wrong figure is worse than an admitted gap — the whole repo is built on marking
UNVERIFIED claims as such.

So measure it:

```sh
pkg install python vulkan-tools
python3 tools/device/device.py --digest
```

Paste the digest. Every question below becomes answered rather than assumed.

## The one that decides Phase 2

**Adreno or Xclipse?** This is the single most consequential fact about the
device, because it decides whether the Phase 2 reference oracle is realistic:

| | Adreno | Xclipse |
|---|---|---|
| Open Vulkan driver | Mesa/Turnip, mature | none mature |
| Box64 + Wine + DXVK stack | works; Winlator-class apps depend on it | vendor driver only |
| Phase 2 viability | good | substantially harder |

### What the model number says

`SM-F971U` decomposes as: `SM-F9xx` is the Galaxy Z Fold family, and the **`U`
suffix is the US carrier/unlocked variant**.

That matters, because US variants of Samsung flagships have consistently
shipped Qualcomm parts — and therefore Adreno — even in generations where other
regions received Exynos parts with Xclipse graphics. The Fold line has also been
Snapdragon-consistent across regions for several generations.

**So the expectation is Adreno, and Phase 2 is probably viable.**

Stated precisely: that is an inference from Samsung's naming conventions and
past regional patterns, not a reading of this unit's hardware. It is a strong
prior, not a measurement. `device.py` reports it as `soc_prior` and then
confirms or overturns it from the actual Vulkan driver — which is the only
thing that actually settles it.

Run the probe before committing effort to Phase 2. The prior says you probably
will not be disappointed.

## The other things the probe settles

- **Texture formats.** ASTC is near-certain; the block sizes supported decide
  the `budget.py` texture factor. Desktop BC support is *not* assumed — the
  probe reports it rather than hoping, and if BC is absent, transcoding moves
  from optimization to hard requirement.
- **Free storage.** The digest checks it against all three budget profiles
  (~6.7 / ~9.5 / ~20.9 GB) and names the shortfall. A 41 GB source install
  plus a multi-gigabyte converted output on one device needs planning.
- **RAM.** Decides the streaming budget. Note that an Android app does not get
  all of it — `dalvik.vm.heapgrowthlimit` caps the managed heap, and a native
  renderer's budget is a separate question from the phone's headline figure.
- **CPU clusters.** Conversion work in Phase 3 is embarrassingly parallel and
  wants the big cores.
- **Vulkan API version and driver.** Sets the floor for the Phase 4 renderer.

## Developing on a phone: an honest assessment

Not a warning — a sequencing note. Some phases are fine, one is not.

| Phase | On-device | Notes |
|---|---|---|
| 1 — Data archaeology | **Fine** | Pure-Python, stdlib-only, no build step. Termux runs it unchanged. |
| 2 — Translation layer | **Fine, arguably better** | Winlator-class stacks are installed APKs, not built ones. The target *is* the dev box; zero deploy friction. |
| 3 — Asset pipeline | **Works, slowly** | Converting tens of GB of textures on a phone SoC means hours-to-days and thermal throttling. Correctness is fine; throughput is the problem. |
| 4 — Native runtime | **The hard one** | Termux has clang, cmake and ninja, so compiling is possible. Building and signing an APK on-device is unusual, and there is no Android Studio, no profiler UI, and awkward debugging. |

Phases 1–3 need no other machine. Phase 4 is where a PC starts to earn its
keep — and that is far enough out that it is not worth solving now.

## Foldable-specific considerations

Two displays with different sizes and aspect ratios, plus a fold transition
while running. For Phase 4 this is real design work, not a detail:

- Render target sizing has to handle both panels, and switching between them
  without tearing down the swapchain badly.
- The inner panel's aspect ratio is far from the 16:9 Prey's UI was laid out
  for. HUD and menu scaling need attention.
- **Thermals.** A foldable is thin, with less mass to sink heat than a slab
  phone. Sustained 3D load will throttle sooner. Benchmarks taken in the first
  minute will overstate what an hour of play delivers — worth measuring over a
  sustained run, not a burst.

## Current status — first probe complete

Run on 2026-09-21. The decisive question is answered.

### Measured

| Fact | Value | Source |
|---|---|---|
| Model | `SM-F971U` (codename `h8q`) | `ro.product.model` |
| ABI | `arm64-v8a` | `ro.product.cpu.abi` |
| Android | 17 (SDK 37) | `ro.build.version.*` |
| SoC | `SM8850`, platform `canoe` | `ro.soc.model` |
| **GPU family** | **Adreno** | `ro.hardware.egl` |
| OpenGL ES | 3.2 | `ro.opengles.version` |
| CPU | 8 cores, clusters at 4742 / 3628 MHz | `sysfs` |
| RAM | 10.83 GB total, 3.09 GB free at probe time | `/proc/meminfo` |
| Storage | 26.64 GB free of 221.50 GB | `statvfs` |

**`SM8850` is a Qualcomm part number and `ro.hardware.egl` reports `adreno`.
Snapdragon and Adreno are confirmed, so Turnip applies and Phase 2 is viable.**
The `soc_prior` inference from the `U` suffix held.

### GPU — measured

The first Termux run reported `deviceName = llvmpipe`, Mesa's **software
rasterizer on the CPU**, because Termux's loader picked up its own Mesa build
instead of the vendor ICD. Its texture-format answers described the CPU and
were meaningless here. `device.py` now detects software rasterizers and refuses
to present their capabilities as measurements.

The real figures come from report **51937** on vulkan.gpuinfo.org:

| Property | Value |
|---|---|
| `deviceName` | **Adreno (TM) 840** |
| `driverName` | Qualcomm Technologies Inc. Adreno Vulkan Driver |
| `driverVersion` | 512.842.19 |
| `apiVersion` | **1.4.295** |
| `deviceType` | `INTEGRATED_GPU` |
| `vendorID` / `deviceID` | `0x5143` / `0x44050A31` |

### Texture compression — all four families supported

| Feature | Value |
|---|---|
| `textureCompressionASTC_LDR` | **true** |
| `textureCompressionASTC_HDR` | **true** |
| `textureCompressionBC` | **true** |
| `textureCompressionETC2` | **true** |

Confirmed against the per-format table, not just the feature bits: `BC1_RGB`,
`BC3`, `BC5`, `BC7_UNORM`, `BC7_SRGB`, `ASTC_4x4`, `ASTC_6x6`, `ASTC_8x8` and
`ETC2_R8G8B8` all report optimal-tiling support with `SAMPLED_IMAGE`.

**`textureCompressionBC = true` contradicts what this document previously
expected.** Desktop BC support is not typical on mobile GPUs, and the earlier
prediction was that transcoding would be a hard requirement. It is not.

The consequence is a genuine de-risking of Phase 3: Prey's shipped BC1/BC3/BC5/
BC7 textures can be sampled by this GPU directly, so a working build needs no
transcoder at all. Dropping mip levels alone produces a usable, shippable
result. Transcoding to ASTC stays worthwhile for size — ASTC 6x6 is 3.56 bpp
against BC7's 8 — but it is now an optimization to schedule, not a blocker to
clear. `budget.py` prices both via the `passthrough` profile.

## Two constraints the probe surfaced

### Memory is tighter than the headline

10.83 GB total, and 3.09 GB actually available with normal apps resident.
Android will evict background apps for a foreground game, so the real figure
under load is higher — but it is not 10 GB. A streaming budget in the 3–5 GB
range is the realistic planning assumption for Phase 4, and
`dalvik.vm.heapgrowthlimit` caps the managed heap separately from native
allocations.

### On-device conversion needs ~50 GB, not ~10

The original budget check compared free space against the *converted output*
only. That was wrong: converting requires the 41 GB source install present
alongside its output, so the peak is the sum.

| | Output alone | During conversion |
|---|---|---|
| aggressive | 6.7 GB | 47.7 GB |
| balanced | 9.5 GB | 50.5 GB |
| quality | 20.9 GB | 61.9 GB |

Against 26.64 GB free, the output fits comfortably and the conversion does not.
`device.py` now reports both.

Freeing space solves it. So does a cheaper option worth considering first:
**incremental conversion** — process one archive at a time and release each
source as its output lands, which keeps the peak near `output + largest single
archive` instead of `output + entire install`. That is a Phase 3 design
decision, recorded here so it is made deliberately.
