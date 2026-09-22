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

### One caveat on promoting a claim

Two kinds of fact live in this document, and they do not carry equal weight:

- **Content facts** — a `.cgf` chunk header layout, a DDS pixel format, whether
  Lua is bytecode. These come from the bytes of individual files and are
  unaffected by how the install was assembled.
- **Layout facts** — which compression methods CryPak uses, entry ordering,
  archive structure. These describe how the *archive* was built, so they are
  only evidence about the developer's pipeline if the archive is the one the
  developer shipped.

An install whose archives were rebuilt by other tooling still yields perfectly
good content facts, but its layout facts belong to whatever rebuilt it.

`probe` checks this and reports a provenance verdict, by reading the ZIP
"version made by" field and entry timestamps — a `consistent` verdict means one
writer signature across the install; `mixed` means more than one. When the
verdict is `mixed`, treat layout claims as weak and content claims as normal.

This is a data-integrity question and nothing more. It says nothing about where
a copy came from — a repack is a repack however it was obtained, and a bit-exact
copy of retail media is bit-exact however it arrived.

### Repacked installs specifically

Repacks vary in ways that matter here, and the verdict distinguishes them:

- Some compress only the *installer payload* and restore the original archives
  byte-for-byte. Provenance comes back `consistent` and everything is usable.
- Some recompress the `.pak` archives themselves. Provenance comes back
  `mixed`; content facts stay good, layout facts describe the repacker.
- Most strip optional content — additional language audio, sometimes video.
  Archives will simply be missing from the inventory.

Do not assume the worst case. Run the probe and read the verdict.

That third point has a useful side effect: a repack is often **substantially
smaller** than the retail install. Against the 26.64 GB free measured in
`DEVICE.md`, that may be the difference between fitting and not — check the
real on-disk size rather than assuming ~41 GB.

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

Run the probe against a real install and promote entries in this file from
UNVERIFIED to VERIFIED against what it reports:

```sh
python3 tools/probe/probe.py "/path/to/Prey" -o prey-report.json
```

A single run settles, at minimum: which compression methods CryPak actually
uses, the real extension inventory, the `.cgf`/`.chr` chunk header layout and
version numbers, the audio middleware (from the ATL implementation DLL), and
whether Lua ships as source or bytecode — five of the open questions in
`ARCHITECTURE.md`, from one command.

The game data itself never has to move. See `GETTING_DATA.md`.
