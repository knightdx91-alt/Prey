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

### Not measured — the Vulkan section was contaminated

The first run reported `deviceName = llvmpipe (LLVM 21.1.8, 128 bits)`, which
is **Mesa's software rasterizer running on the CPU**, not the Adreno driver.
Termux's Vulkan loader picked up its own Mesa build instead of the vendor ICD.

Everything in that section described the CPU. In particular
`astc_ldr=False, etc2=False` is llvmpipe's answer and says nothing about this
device — taken at face value it would have condemned the entire asset pipeline
strategy for no reason.

`device.py` now detects software rasterizers and refuses to present their
capabilities as measurements. Still open:

- Vulkan API version on the actual Adreno driver
- Texture format support — ASTC block sizes, ETC2, and whether desktop BC is
  present at all
- The Adreno model number

Termux is the wrong tool for this. It needs a native Android app holding a real
Vulkan device.

**Use Vulkan Hardware Capability Viewer** (Sascha Willems) — open source, on the
Play Store, with APKs on GitHub. It enumerates per-`VkFormat` support rather
than just summarizing the GPU, which is exactly the table needed here. It also
has an export/share function, so the report can travel as a file instead of
screenshots.

What to capture from it:

| Tab | What matters |
|---|---|
| Device | `deviceName` (the Adreno model), `apiVersion`, `driverVersion` |
| Features | `textureCompressionASTC_LDR`, `textureCompressionETC2`, `textureCompressionBC` |
| Formats | Which `VK_FORMAT_ASTC_*` block sizes are supported, and whether any `VK_FORMAT_BC*` appears at all |

The formats tab is the one that decides the texture pipeline. The ASTC block
sizes available set the `budget.py` texture factor; today it assumes ASTC 6x6.

> The public database at vulkan.gpuinfo.org may already hold a report for this
> SoC, which would answer the same questions without installing anything. Its
> results pages are JavaScript-rendered, so they could not be read from here —
> worth a look in a browser, but the app is the path that definitely works.

Expected, pending that measurement: ETC2 present (Vulkan on Android requires
it), ASTC LDR present (universal on Adreno for many generations), desktop BC
absent. If BC is indeed absent, transcoding is confirmed as a hard requirement
rather than an optimization — which is what `budget.py` already assumes.

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
