# Architecture

## The gap we are closing

| | Prey as shipped | Android target |
|---|---|---|
| ISA | x86-64 | ARM64 (AArch64) |
| OS | Windows (Win32, PE) | Android (Bionic, ELF) |
| Graphics | Direct3D 11 | Vulkan 1.1+ |
| Engine | Arkane fork of CryEngine | — |
| Scripting | Lua | Lua (portable) |
| Audio | Wwise **(UNVERIFIED)** | AAudio / OpenSL ES |
| Input | KB/M + XInput | Touch, gamepad |
| Memory | Desktop-class, no hard cap | 4–12 GB shared with the OS |

Five of those rows are mechanical translation problems with known solutions.
The engine row is the whole project.

## Why the engine row is hard

CryEngine is source-available, which sounds like it solves everything. It does
not. Prey runs on Arkane Austin's fork, and the delta between that fork and any
public CryEngine drop is both large and undocumented — gameplay systems,
renderer changes, the GOO/mimic material work, the save system, and whatever
format revisions came with them. Stock CryEngine source is a **reference for
how these formats are shaped**, not a drop-in runtime for this game's data.

So the working assumption is: every format is Prey's format until bytes prove
it matches stock CryEngine.

## Two tracks

### Track 1 — data archaeology (starts first)

Unpack and document the shipped data. Archives, then geometry, textures,
materials, levels, audio banks, Lua.

This track is first because it is the one that cannot be skipped. Whichever
runtime path wins, the game's data has to be readable, and on Android it has to
be *re-encodable* — desktop BC7 textures and uncompressed vertex streams are
not what you want to be streaming off eMMC into 6 GB of shared RAM.

It is also the only part of the project that gives fast, honest feedback: a
parser either reproduces a known-good asset or it does not.

### Track 2 — runtime

**2a. Translation layer.** Box64 or FEX-Emu for the ISA, Wine for the Win32
surface, DXVK for D3D11→Vulkan, Turnip/Mesa for Adreno. Every piece exists and
is used in anger by the Winlator-class projects.

Expect it to be slow. A modern CryEngine title, x86-emulated, through two
graphics translation layers, on a phone SoC, is not a playable configuration.
That is fine — this track is not trying to be playable. It is trying to be a
**reference implementation**: the thing that renders a frame correctly so the
native renderer has something to diff against, and the thing that proves the
extracted data is complete.

**2b. Native runtime.** An ARM64 Android application: Vulkan renderer, Lua VM,
physics, audio, and the game systems, consuming data from Track 1's pipeline.
This is a multi-year effort and the only path to a build that is actually worth
playing.

The two tracks are not sequential and not competing. 2a is the oracle, 2b is
the product.

## Build shape (planned, not yet present)

```
app/          Android application, Gradle + NDK, ARM64 only
engine/       Native runtime — renderer, resource system, game code
tools/        Host-side data tooling (Python + native)
third_party/  Vendored dependencies
```

Only `tools/` exists today. The rest lands when Track 1 has enough of the data
model pinned down to make the runtime's resource layer more than a guess.

## Open questions

These are open because nobody has looked at the bytes yet. They are written
down so the answers can be recorded against them, not because they are
rhetorical.

1. Are Prey's `.pak` archives readable as plain ZIP, or does CryPak's custom
   header/compression path (and any encryption) get in the way?
2. Which CryEngine geometry chunk versions does Prey use, and how far do they
   sit from the public `CryHeaders` definitions?
3. Wwise or FMOD for audio, and which SDK version?
4. Total installed size, and the size after re-encoding textures for mobile —
   this decides whether the game ships as an install or a streamed asset pack.
5. How much of the renderer's behavior is data-driven enough to reproduce
   without the fork's source?
