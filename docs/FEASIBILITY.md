# Feasibility

An honest assessment of what this project is asking for, phase by phase. The
short version: three of the four phases are achievable, and the fourth is not a
port at all — it is a reimplementation, which is a different and much larger
thing.

## The scale of each phase

| Phase | Effort | Solo-achievable | Confidence |
|---|---|---|---|
| 1 — Data archaeology | weeks–months | **yes** | high |
| 2 — Translation layer | days–weeks | **yes** | high (that it can be *tried*) |
| 3 — Asset pipeline | months | **yes** | high |
| 4 — Native runtime | team-years | **no** | high |

## Phase 4 is mislabelled, and it matters

The roadmap calls Phase 4 a "native runtime," which makes it sound like the
last step of a port. It is not a port. Consider what would actually have to be
written:

Prey runs on Arkane Austin's fork of CryEngine. CryEngine is source-available,
which sounds like it solves the problem, and does not. What the public source
does not contain:

- Arkane's renderer modifications
- Arkane's gameplay systems — the GLOO gun, mimics, neuromods, the save system
- The game logic that makes Prey *Prey* rather than a CryEngine tech demo

So building Phase 4 means writing a Vulkan renderer matching a modified
CryEngine's feature set, plus physics, animation, audio, AI and scripting
integration, **and then reimplementing the game on top of it** — from a
stripped x86-64 binary, with no decompilation project to build on.

That is not porting. That is what OpenMW, devilutionX and Ship of Harkinian
do, and the comparison is not flattering:

| Project | Target | What it had | Time |
|---|---|---|---|
| devilutionX | Diablo (1996) | full decompilation of a ~1.4 MB binary | years |
| OpenMW | Morrowind (2002) | open reimplementation, large team | 15+ years, ongoing |
| Ship of Harkinian | Ocarina of Time (1998) | a community N64 decompilation effort | years, many people |
| **this** | **Prey (2017)** | **nothing equivalent** | — |

Every one of those targets is older, smaller and simpler than Prey, and every
one had either a decompilation to build from or an existing open engine. None
of that exists here, and no amount of clever tooling substitutes for it.

Phase 4 as written should be treated as out of scope, not as distant.

## "Port" means four different things

The earlier assessment answered only the hardest reading of the word and
treated the others as if they were not ports. That was too narrow. Ranked by
difficulty:

### 1. Bundled-stack APK — **achievable**

Ship the translation layer *inside* an Android app. A single APK containing a
preconfigured Wine prefix, Box64, DXVK, the driver, and a launcher that boots
straight into the game. The user taps an icon and Prey starts. No Winlator UI,
no container setup, no drive mapping.

Under the hood it is still translation. From every practical angle — install,
icon, launch, play — it is an Android port. The components are open source and
this is largely integration work: take a working container configuration and
wrap it.

**This is almost certainly what "an Android port" should mean for this
project.** It is reachable solo, and the work is assembly rather than
invention.

### 2. Static recompilation (AOT) — **research-grade**

Instead of translating x86-64 at runtime, translate the whole binary to native
ARM64 *ahead of time*, then compile and link it. The output is genuinely native
code, and the per-instruction emulation overhead disappears.

This is a real technique — it is how several N64 titles got true native ports,
via tooling that statically recompiles the ROM to C. Applying it to a modern
x86-64 Windows binary is far harder: variable-length instructions, indirect
jumps, dynamic linking, exception handling and TLS all resist static analysis
in ways an N64 ROM does not. Nothing production-grade exists for a title of
this size.

It also would not remove the dependency on Win32 and D3D11 — those still need
Wine and DXVK underneath. So it is a **performance optimization on path 1**,
not an escape from it.

Worth knowing about. Not worth starting with.

### 3. Engine substitution — **partial, useful for other reasons**

CryEngine itself has had Android as a build target. A stock CryEngine build on
Android could plausibly load some of Prey's assets — but Prey's *game* lives in
its compiled binary, not in its data, so this yields an engine that renders
Prey's art and does not play Prey.

Not a path to the goal. Genuinely useful for Phase 1 and 3, though: an
independent renderer that can open extracted assets is a strong way to validate
that the format parsers are correct.

### 4. Full reimplementation — **out of reach**

Covered above. The blocker is the absence of a decompilation. devilutionX had
one for a ~1.4 MB binary; Prey is tens of megabytes of optimized C++, and a
matching decompilation at that scale is a multi-year effort for a substantial
team. Nobody has attempted it.

If that ever existed, path 4 opens. Until then it does not.

## What the finished thing actually feels like

Separate question from whether it runs, and worth being blunt about early.

### Out of the box: a Windows game on a phone screen

Launched through Winlator as-is, Prey renders inside a Wine desktop. A mouse
cursor. Windows menus. A HUD laid out for a monitor at desk distance. Controls
expecting a keyboard and mouse, with touch standing in for a mouse badly.

It is Prey-for-Windows displayed on Android. Nothing about it is Android.

### What can be fixed, by layer

| Layer | Achievable? | How |
|---|---|---|
| **Launch experience** | **fully** | The bundled APK (Phase 3.5). Tap an icon, go straight into the game, never see a container UI. Indistinguishable from launching any Android app. |
| **Controls** | **largely** | These stacks ship touch-input mapping — on-screen sticks and buttons bound to keys, touch-to-look. This is how people actually play PC games on phones. Good, not native-feeling. |
| **Resolution / quality** | **yes** | CryEngine titles are heavily configurable through console variables and config files. Worth checking which ones Prey exposes — that is Phase 1 work paying off somewhere unexpected. |
| **HUD and UI scale** | **partly** | Depends entirely on what the game exposes. If UI scale is a cvar, it is a config edit. If it is baked into the UI assets, it means modifying the game. |
| **Performance tuning** | **yes** | The asset pipeline. Lower-resolution textures cut memory pressure and bandwidth, which is the constraint that actually bites on mobile. |

### The honest ceiling

**It will not feel like a game built for Android, and no amount of work in
scope here changes that.**

Prey was designed for mouse and keyboard, at desk distance, on a 16:9 monitor,
by people who assumed a GPU with dedicated VRAM. Translation gets it running.
Input mapping makes it playable. Asset work makes it fit and hold a framerate.
None of that redesigns the game for a phone — that would mean modifying the
game itself, which lands back in the reimplementation problem.

The realistic target is **"a PC game that plays well on this device,"** not
"a phone game." Set expectations there and the result is satisfying. Set them
at the other one and it never will be.

### One genuine advantage

The reference device folds open to roughly 8 inches. That is a far better
surface for a desktop-designed HUD than a normal phone, and it materially
improves the input-mapping experience — there is room for on-screen controls
that do not cover what you are looking at. The foldable is an asset here, not
just a thermal liability.

## The ladder

Work them in order, because each stage produces something usable and informs
the next:

1. **Get it running in Winlator at all.** Bounds everything else.
2. **Tune it** — driver, Box64 settings, resolution, asset pipeline — until it
   is actually playable.
3. **Bundle that configuration into an APK.** Now it is an Android port in the
   sense that matters.
4. *Optionally*, explore static recompilation to close the emulation gap.

Stages 1–3 are a real project with a real endpoint. Stage 4 is a research
project that may never pay off, and nothing before it depends on it.

## What is actually achievable

Reframe the goal from *"reimplement Prey natively"* to **"a tap-to-play
Android app that runs Prey acceptably."** That version is real, and it is
mostly assembly rather than invention:

1. **Translation layer** — Box64/FEX for the ISA, Wine for Win32, DXVK for
   D3D11→Vulkan, Turnip for Adreno. All of it exists and is maintained by
   others. Winlator-class projects already run substantial PC games this way.
   The work here is configuration and troubleshooting, not engineering.
2. **Asset pipeline** — shrink the install and cut texture memory pressure so
   the thing fits and streams acceptably. This is where the repo's tooling
   already points, and it is the part that genuinely benefits from custom work.
3. **Device tuning** — resolution, settings, thermal behaviour, the foldable's
   two panels.

That path produces "Prey running on a Galaxy Z Fold." It is not a native port,
and it is a real result.

## What the measurements have already settled

The device work has been unusually kind so far:

- **Adreno 840, Vulkan 1.4.295.** Turnip applies, so the translation-layer
  stack is viable rather than speculative. This was the single biggest risk and
  it landed well.
- **BC texture support.** The GPU samples Prey's shipped textures directly, so
  no transcoder is needed for a working build. An entire pipeline stage becomes
  optional.
- **Storage and RAM are workable**, with the conversion-peak caveat in
  `DEVICE.md`.

None of that makes Phase 4 achievable. All of it makes the achievable path
easier than it looked a week ago.

## The honest unknowns

- **Performance through the translation stack.** Prey is a 2017 AAA title.
  Box64 costs CPU, DXVK costs some GPU, and a foldable throttles under
  sustained load. Whether the result is playable or a slideshow is genuinely
  unknown, and no amount of reasoning settles it.
- **Whether Prey specifically runs under Wine on ARM.** Individual titles fail
  for individual reasons — anti-tamper, a driver path, one unimplemented call.
- **RAM headroom.** 10.83 GB total with ~3 GB free at rest, against a game
  that expects 8 GB+ on desktop.

## The cheapest next experiment

Before committing months to asset tooling, spend an evening on this:

> Install a Winlator-class Windows-on-Android environment and try to launch
> Prey through it.

That single test answers more about the project's ceiling than any further
analysis. It tells you whether the game boots at all, roughly what performance
looks like, and which subsystems fail first — and those failures are a work
list. If it boots at 15 fps, the asset pipeline has a clear target. If it does
not boot, that is worth knowing before building tooling to feed it.

Phase 1 work remains worth doing regardless: the format knowledge is needed for
any path, and it is the part that is unambiguously achievable.
