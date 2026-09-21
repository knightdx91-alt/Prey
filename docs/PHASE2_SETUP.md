# Phase 2 — picking a translation layer

> **Staleness warning.** The Winlator ecosystem moves fast: forks appear,
> overtake the mainline, and get abandoned within months. The specific names
> below are from training data with a mid-2026 cutoff and could not be verified
> from this session — GitHub is scope-blocked here. **Check current community
> sources before trusting any name in this file.** The technical reasoning
> further down does not go stale; the project names might.

## The variable that actually matters

It is not which Winlator fork. It is **the GPU driver**.

These apps are all roughly the same stack — Box64 or FEX for the ISA, Wine for
Win32, DXVK for D3D11→Vulkan — wrapped differently. What separates a playable
result from a slideshow is the Vulkan driver underneath, and on Adreno that
means Mesa's **Turnip**.

Here is the specific risk for this device: **Adreno 840 is new.** Turnip
support for a freshly released Adreno generation typically lags the hardware,
sometimes by months. If Turnip does not yet handle Adreno 840 well, no choice
of wrapper fixes it.

So the first question to answer is not "which app" but:

> Does current Turnip support Adreno 840, and how well?

Most Winlator-class apps let you select or import a graphics driver. Expect to
try several:

1. **Turnip**, newest build available — the preferred path when it works
2. **An older Turnip** — newer is not always better on new silicon
3. **The vendor Adreno driver** (Qualcomm 512.842.19, already measured) via
   whatever passthrough the app offers — sometimes the only thing that works on
   brand-new parts, sometimes faster, sometimes broken with DXVK

Measured, from `docs/DEVICE.md`: Vulkan 1.4.295, Qualcomm driver 512.842.19,
Adreno 840. That is a modern Vulkan level, so the hardware is not the
constraint — driver maturity is.

## Where to get it

Not on the Play Store — these are sideloaded APKs, published on each project's
own GitHub releases page:

| Build | Source |
|---|---|
| Winlator (mainline) | `github.com/brunodev85/winlator` → Releases |
| Winlator Cmod | `github.com/coffincolors/winlator` → Releases |

Install on Android:

1. Open the releases page in Chrome on the phone and download the `.apk`
2. Android prompts about installing from an unknown source — allow it for
   Chrome when asked
3. Open the downloaded file to install

The APKs are large (Wine and its dependencies are bundled), and some builds
fetch further components on first run, so do this on wifi.

Take these from the projects' own release pages rather than an APK mirror
site. Mirrors repackage installers, and a repackaged APK is a common malware
vector — an engineering hygiene point, nothing more.

## Builds to try, in order

Named with the staleness warning above firmly in mind.

1. **Winlator (mainline, brunodev85)** — the reference implementation. Best
   documented, largest community, most troubleshooting material. Start here
   because when something breaks, this is the one people can help with.
2. **Winlator Cmod (coffincolors)** — a fork frequently reported as faster,
   with more aggressive Box64 tuning and quicker releases. The usual second
   stop when mainline performance disappoints.
3. **Bionic-based builds** — variants linking Android's own libc instead of
   bundling glibc. Generally lower overhead. Naming here changes often.
4. **Mobox**, **GameHub / GameNative**, and other alternatives — different
   wrappers over a similar stack. Worth trying if the above stall.

Do not over-invest in choosing. Install one, get a result, and let the failure
mode tell you whether to switch. They are APKs and coexist happily — installing
two costs storage, not time.

### Mainline vs. a performance fork

The reliable distinction is structural, not a feature list. Mainline is the
reference implementation: conservative release cadence, broadest testing, and
the version every troubleshooting thread assumes. Forks exist because that
cadence is slow relative to how fast the underlying components move, so they
track Box64, Wine, DXVK and the graphics drivers more aggressively.

What forks typically change, in rough order of impact:

| Area | Why it matters |
|---|---|
| **Bundled graphics drivers** | Which Turnip builds ship, and whether vendor-driver passthrough is offered. The single biggest lever on new Adreno silicon. |
| **Box64 version and tuning presets** | Directly sets CPU emulation overhead. |
| **Wine version** | Newer Wine means better per-title compatibility. |
| **DXVK version** | Matters for D3D11 titles, which includes Prey. |
| **libc** | Bionic-linked builds carry less overhead than bundled glibc. |
| **UI and container management** | Per-game profiles, input mapping. Convenience, not performance. |

### Which to reach for on Adreno 840

The driver row decides it. New silicon is exactly the case where mainline's
conservative bundling hurts — a fork shipping newer or more numerous Turnip
builds has better odds of having something that handles an Adreno 840 at all.

Against that, mainline is what the community documents, so when something
breaks it is the one people can help with.

Practical resolution: **install both.** Check the graphics driver list in each
before running anything. Whichever offers more options for this GPU is the one
to try first; keep the other for when you need to ask someone why something
broke.

> Confidence: the structural distinction and the table above are stable
> characteristics of how these forks work. Which specific fork is currently
> fastest, best maintained, or even still alive is **not** verifiable from this
> session and changes on a scale of months.

## Getting the game into a container

### The concept

Winlator runs **containers** — each one a Wine prefix, i.e. a self-contained
virtual Windows install with its own `C:` drive. That `C:` lives in the app's
private storage.

**Do not copy the game into `C:`.** At ~41 GB that bloats app storage, is
awkward to manage, and has to be redone for every container you try. Instead,
leave the game where it is on shared storage and **map a drive letter to its
folder**. Wine then sees it as `D:` (or whatever letter) and runs it in place.

This is the part that is stable across forks and versions. Menu names below may
differ — the mechanism will not.

### Steps

1. **Put the game on shared storage, extracted.** Somewhere like
   `/storage/emulated/0/Games/Prey/`. If it arrived compressed, extract it
   first — Wine needs the real directory tree, with `Prey.exe` and the data
   folders beside it. Confirm the `.exe` is actually present before continuing.

2. **Create a container.** Containers tab → `+`. Settings worth setting now:

   | Setting | Value |
   |---|---|
   | Graphics driver | the Turnip / vendor-driver question — see above |
   | DXVK | a recent version; Prey is D3D11 |
   | Box64 preset | start at the default; tune later |
   | Screen size | start low, e.g. 1280x720 |
   | RAM / Windows version | defaults are usually fine |

3. **Map a drive to the game folder.** In the container's settings there is a
   **Drives** section. Add one pointing at the folder from step 1. It will
   appear inside Wine as `D:\` or similar.

4. **Launch it.** Start the container, and from the Wine desktop open the file
   manager, navigate to the mapped drive, and run `Prey.exe`. Most builds also
   let you save a shortcut to that executable so later launches skip the
   browsing.

### If it came as an installer

If what you have is `setup.exe` rather than an installed game folder, run the
installer *inside* a container first and let it install to the container's
`C:`. Bear in mind the ~41 GB then lands in app private storage, so prefer an
already-installed folder where possible.

## Prey-specific concerns

- **D3D11 → DXVK.** The well-trodden path; better supported than D3D12 or
  older D3D9 titles.
- **CryEngine's deferred renderer is bandwidth-hungry.** Mobile memory
  bandwidth is far below desktop. Expect resolution to matter more than any
  other setting — drop it first and hardest.
- **RAM is the tight one.** `DEVICE.md` measured 10.83 GB total with ~3 GB free
  at rest. Wine, DXVK and Prey together against that is the constraint most
  likely to bite. Close everything before launching.
- **Thermals.** A foldable throttles sooner than a slab. Whatever the first
  minute shows, the tenth minute is the real number.
- **Storefront wrapper.** Retail builds carry a storefront DRM layer that has
  to initialize under Wine. This is a common early failure point and usually
  the first thing to diagnose if it will not launch.

## What to report back

Whatever happens, these are the useful facts:

1. Which app and version, and which graphics driver was selected
2. Does it reach the main menu? If not, where does it fail?
3. If it runs: frame rate at the lowest settings and resolution, taken after
   ~10 minutes rather than immediately
4. What fails first — a crash, a missing shader, audio, input

Failures are the deliverable here. A list of what broke is a work plan; a
working build is a bonus.

## Why this is the right next step

It is cheap — an evening — and it bounds the whole project. See
`FEASIBILITY.md`: Phase 4 is out of scope, so the translation layer is the
primary path rather than a reference oracle. What it does tells you where the
asset pipeline should aim, and what it cannot do tells you that now rather than
after months of tooling.
