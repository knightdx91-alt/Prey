# Asset formats

Prey's data is CryEngine-shaped, filtered through Arkane Austin's fork. This
document is the running record of what those formats actually are.

## How to read this document

Every claim carries a confidence marker:

- **VERIFIED** — somebody parsed the bytes from a real Prey install and it held.
  Record the file, the offset, and what was found.
- **UNVERIFIED** — inferred from public CryEngine documentation or from how
  other CryEngine titles behave. Useful as a starting hypothesis. Not a fact.

Nothing here is VERIFIED yet. This is a map of where to dig, written before the
digging. Promote entries as evidence arrives, and say what the evidence was.

## Archives — `.pak`

**UNVERIFIED.** CryPak archives are ZIP containers. CryEngine writes a custom
end-of-central-directory record alongside the standard one, supports compression
methods beyond deflate (store, deflate, and CryEngine-specific codecs), and has
historically supported per-file encryption in some configurations.

Practical consequence: a stock ZIP reader gets you a long way and then stops. It
will enumerate most entries and decompress the stored/deflated ones. Entries
using a custom codec, and any encrypted entry, need CryPak-aware handling.

`tools/paktool/` is built around exactly that expectation — it reads what the
standard path can read and reports precisely what it could not, rather than
failing the whole archive.

Expected locations in a Prey install, to be confirmed against a real one:

```
GameSDK/GameData.pak
GameSDK/Levels/<level>/level.pak
Engine/*.pak
```

## Geometry — `.cgf`, `.cga`, `.chr`, `.skin`

**UNVERIFIED.** Chunked format. A file header identifies the format and points
at a chunk table; each chunk carries a type, a version, and an offset. Mesh
data, material references, skeleton and skinning data all arrive as chunk types.

The version numbers are the thing to look at first. Public `CryHeaders.h` gives
the stock chunk types and versions; where Prey's differ, the delta is Arkane's
and has to be reverse-engineered directly.

## Textures — `.dds`

**UNVERIFIED.** DDS containers, but CryEngine splits mips across companion
files (`.dds.1`, `.dds.2`, …) for streaming, and the base file may carry a
CryEngine-specific tail after the standard DDS payload.

Desktop block formats (BC1/3/5/7) are the likely contents. **These do not
survive contact with Android unmodified** — BC support on mobile GPUs is not
something to rely on. Transcoding to ASTC is a required pipeline stage, not an
optimization, and it is why the extraction tooling needs to produce something
re-encodable rather than just something openable.

## Materials — `.mtl`

**UNVERIFIED.** XML, possibly in CryEngine's binary XML encoding rather than
text. Binds shader names, parameters, and texture slots.

## Levels

**UNVERIFIED.** Per-level `.pak` containing terrain, object layers, entity
definitions, and navigation data. Prey's Talos I is a single continuous station
with heavy streaming between sections; expect the level structure to reflect
that rather than the open-terrain layout CryEngine documentation assumes.

## Audio — `.bnk` / `.pck`

**UNVERIFIED, and the engine is genuinely in question.** CryEngine routes audio
through an Audio Translation Layer with both Wwise and FMOD implementations.
Which one Prey uses needs confirming by looking at the shipped DLLs and the
audio data layout, not by recall.

## Scripting — Lua

**UNVERIFIED.** CryEngine embeds Lua. Scripts may ship as source or as
precompiled bytecode; bytecode would be Lua-version- and endianness-specific,
which matters when the target is ARM64.

## Next

Open a real install, run `paktool stats` against it, and start promoting things
in this file from UNVERIFIED to VERIFIED. The tooling is written to make the
first step cheap; the value is in recording what it finds.
