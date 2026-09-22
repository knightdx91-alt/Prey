# Size budget

**Measured 2026-09-22** from the reference install: **59.5 GiB uncompressed,
29.3 GiB compressed on disk**, across 116 archives and 264,336 entries.

The earlier ~41 GB figure was a headline download size and did not match this
install. Both real numbers now replace it: 29.3 GiB is what occupies disk,
59.5 GiB is what the asset pipeline actually has to process.

Two entirely separate problems hide inside that. They get confused constantly,
and conflating them makes the project look harder than it is.

## Problem 1: getting 41 GB to the agent — doesn't exist

You never send it. The survey workflow in `GETTING_DATA.md` exists precisely
so the data stays put.

For scale: the probe report on this repo's synthetic install is about 8 KB, and
it is built to stay flat as the install grows — signatures deduplicate on their
leading bytes, so the report scales with the number of *distinct formats*, not
with archives times extensions. A 41 GB install repeats a few hundred header
shapes across tens of archives; the second identical header teaches us nothing
the first did not.

Expect a real report in the low megabytes at worst, against 41 GB of game.

Incidentally, the session container has ~30 GB free, so a 41 GB install could
not be held here even if every other obstacle vanished.

## Problem 2: 41 GB onto a phone — real, and the hard one

This one is genuine, and it constrains Phase 3 and Phase 4 both.

Desktop assets are sized for a GPU with dedicated VRAM and a storage budget
nobody was counting. Mobile needs different texture formats, lower resolutions,
fewer locales and cheaper audio. Each of those is a known multiplier, so the
footprint can be estimated before a single byte is converted:

```sh
python3 tools/budget/budget.py --total-gb 41
python3 tools/budget/budget.py --total-gb 41 --all-profiles
python3 tools/budget/budget.py --report prey-report.json   # real category mix
```

### Where it lands

Modelled against the measured 59.5 GiB uncompressed:

| Profile | Result | Reduction | Transcoder |
|---|---|---|---|
| `quality` | ~30.3 GB | 2.0x | yes |
| `passthrough` | ~18.4 GB | 3.2x | **no** |
| `balanced` | ~13.8 GB | 4.3x | yes |
| `aggressive` | ~9.8 GB | 6.1x | yes |

`passthrough` exists because the target GPU supports desktop BC (measured —
Adreno 840, see `DEVICE.md`). Prey's shipped textures can be sampled directly,
so that profile only drops resolution: bits-per-pixel unchanged, pixel count
quarters, factor 0.25 exactly. It costs about 4.6 GB against `balanced` and
needs no transcoder, which makes it the fastest route to something that runs.

Against the phone's measured **26.64 GB free**, only `aggressive` and
`balanced` leave meaningful headroom once the source install is also resident.

### Textures dominate — now confirmed by count, not just assumed

The survey settles what the model had been assuming. Of 264,336 entries,
**184,812 (69.9%) are texture data** — 27,343 `.dds` plus 157,469 split-mip
and alpha companion files. Geometry and animation together account for 41,302;
audio for 13,486.

The category *split by bytes* still comes from the assumed proportions, since
the digest reports counts rather than per-extension sizes. But a file
population that is 70% texture makes the model's 55%-by-bytes assumption look
conservative rather than optimistic.

### The surprise

Run the balanced profile and look at what ends up largest:

```
texture         22.55 GB     0.111     2.51 GB
audio            8.20 GB     0.180     1.48 GB
geometry         4.92 GB     0.600     2.95 GB   <-- now the biggest
```

**Geometry overtakes textures.** Not because there is more of it — there is
roughly a quarter as much — but because its reduction factor is the mildest of
the three. Texture and audio have aggressive, well-understood mobile answers;
geometry does not, so it barely moves and ends up dominating.

That inverts the obvious plan. The instinct is to pour effort into texture
compression, where the raw gigabytes are. The model says texture compression is
the *solved* part, and the open question is mesh data: vertex stream
quantization, LOD policy, and how much of Prey's geometry a phone needs at all.

This conclusion rests on an assumed 55/20/12 split. A real probe report may
move it. But it is the kind of thing worth knowing before committing months to
the wrong subsystem, and it is exactly what a cheap model is for.

### Against delivery ceilings

Even `aggressive` at ~6.7 GB clears no Play ceiling. Play's base module is
measured in hundreds of megabytes and asset delivery in low gigabytes, so the
realistic first target is a sideloaded, OBB-style install — with Play delivery
a later problem, solvable only by cutting content rather than by compressing
harder.

> The specific Play limits in `budget.py` are marked **UNVERIFIED**. They move,
> they differ by delivery mode, and they should be confirmed against current
> policy before anyone plans around them.

## Every number here is an estimate

The reduction factors are derived from format arithmetic and ordinary mobile
practice, not from converting Prey's actual assets. They are a defensible
starting point and an explicit place to be corrected.

Two things sharpen them:

1. **A probe run** replaces the assumed category split with this install's real
   mix — `budget.py --report` does that automatically.
2. **The first real conversions** replace the factors themselves with measured
   ratios. Until then, treat the totals as order-of-magnitude.

The value is not the 9.5 GB figure. It is that 41 GB is now a tractable number
with a named largest problem, instead of an intimidating one.
