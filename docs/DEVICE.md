# Reference device

All work happens on a **Samsung Galaxy Z Fold 8**. That makes it both the
development machine and the target, so its capabilities are project inputs
rather than trivia.

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

**Adreno or Xclipse?**

Samsung ships Snapdragon parts (Adreno GPU) in some regions and Exynos parts
(Xclipse GPU) in others, and the Fold line has historically been
Snapdragon-consistent — but "historically" is not "verified on your unit."

It matters more than any other single fact:

| | Adreno | Xclipse |
|---|---|---|
| Open Vulkan driver | Mesa/Turnip, mature | none mature |
| Box64 + Wine + DXVK stack | works; Winlator-class apps depend on it | vendor driver only |
| Phase 2 viability | good | substantially harder |

If it is Adreno, the reference-oracle path in `ARCHITECTURE.md` is realistic.
If it is Xclipse, Phase 2 needs rethinking before any effort goes into it.
`device.py` reports the family and says which case you are in.

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

## Current status

Nothing here is measured yet. Run `device.py` and the whole table above stops
being conditional.
