# Size budget

Prey Digital Deluxe is roughly **41 GB** installed. That number shapes the
whole port, so it deserves arithmetic rather than a shrug.

Two entirely separate problems hide inside it. They get confused constantly,
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

Using assumed AAA proportions, since no probe report exists yet:

| Profile | Result | Reduction |
|---|---|---|
| `quality` | ~20.9 GB | 2.0x |
| `balanced` | ~9.5 GB | 4.3x |
| `aggressive` | ~6.7 GB | 6.1x |

The texture math is the load-bearing part. Desktop BC7 is 8 bits per pixel;
ASTC 6x6 is 3.56, and halving each dimension quarters the pixel count. That is
`(3.56/8) x 0.25 = 0.111` — a 9x reduction on the single largest category,
and it is ordinary mobile practice rather than anything clever.

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
