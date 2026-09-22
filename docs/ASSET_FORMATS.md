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

**VERIFIED** — 116 archives, 264,336 entries, surveyed 2026-09-22.

Plain ZIP throughout. Every archive parsed with a standard reader; **zero**
were unreadable, and **zero** entries needed CryPak-aware decoding.

| Compression method | Entries |
|---|---|
| deflate | 245,483 |
| store | 18,853 |

That is the whole list. No CryEngine-specific codec, no encryption, nothing
outside the standard ZIP set — which overturns this document's earlier
expectation that a stock reader would "get you a long way and then stop." It
does not stop. `paktool` reads 100% of the shipped data.

Size: **59.5 GiB uncompressed, 29.3 GiB compressed** on disk.

## Geometry — `.cgf`, `.cga`, `.chr`, `.skin`

**VERIFIED.** Chunked format using the **`CrCh` header**, not the legacy
`CryTek\0\0` one, and carrying a **single version — 1862 (0x746)** — across
every geometry and animation type: `.anm`, `.caf`, `.cga`, `.cgf`, `.chr`,
`.chrm`, `.img`, `.skin`, `.skinm`.

One version across the whole install is good news: there is one layout to
reverse-engineer, not a family of them. Header layout confirmed as `CrCh` +
version (u32) + chunk count (u32) + chunk table offset (u32), with observed
table offsets of 16 — i.e. the table follows the header immediately.

Chunk *contents* remain unread; the header and table position are what is
established.

## Textures — `.dds`

**VERIFIED (partially).** DDS containers confirmed by magic (`DDS ` + header
size 124). Split-mip streaming confirmed and larger than expected: the
companion files surface as bare numeric extensions.

| Kind | Files |
|---|---|
| `.dds` base | 27,343 |
| `.1` … `.8` (mip chain) | 121,927 |
| `.a`, `.1a` … `.7a` (alpha chain) | 35,542 |
| **Total texture-related** | **184,812** |

That is **69.9% of all 264,336 entries**. Textures dominate the install by file
count by a wide margin, which corroborates the size model's assumption that
they dominate by bytes too.

The mip companions carry no header — they begin with raw payload, which is why
they appear as UNRECOGNIZED signatures. The `.a` chain starts at the DDS
header's size field, consistent with being a detached alpha surface.

**Still unknown: the pixel format.** The DDS FourCC sits at offset 84, beyond
the 64-byte sample window, so whether this is BC1/BC3/BC5/BC7 is not yet
established. That is the next thing worth reading, and it now matters less
than expected — the target GPU supports BC natively (see `DEVICE.md`).

## Materials — `.mtl`

**UNVERIFIED.** XML, possibly in CryEngine's binary XML encoding rather than
text. Binds shader names, parameters, and texture slots.

## Levels

**UNVERIFIED.** Per-level `.pak` containing terrain, object layers, entity
definitions, and navigation data. Prey's Talos I is a single continuous station
with heavy streaming between sections; expect the level structure to reflect
that rather than the open-terrain layout CryEngine documentation assumes.

## Audio — Wwise

**VERIFIED.** **13,486 `.wem` files** — Wwise's encoded media format. The
middleware question is settled: it is Wwise, not FMOD.

Worth noting what is *absent*: **no `.bnk` soundbanks**. The audio ships as
loose `.wem` media rather than packed banks, which is unusual and simplifies
extraction considerably — individual sounds are addressable without parsing a
bank container.

The probe's own middleware detection reported `UNDETERMINED`, because it
infers from CryEngine ATL implementation DLL names and this install carries
only 20 binaries. The `.wem` inventory is the stronger evidence and overrides
it.

## Scripting — Lua

**VERIFIED.** **419 files, all bytecode. Zero source.**

Bytecode is version- and endianness-bound, which matters directly for an ARM64
target: the bytecode must either be interpreted by a matching Lua build or
decompiled and recompiled. Identifying the exact Lua/LuaJIT variant from the
bytecode header is the follow-up.

## Next

Phase 1's first pass is done — archives, geometry headers, texture layout,
audio middleware and Lua encoding are all measured. What remains:

1. **DDS pixel format.** The FourCC is at offset 84, past the probe's 64-byte
   window. A targeted read of a few `.dds` headers settles whether this is
   BC1/BC3/BC5/BC7.
2. **`.mtl` encoding** — text XML or CryEngine binary XML. Extract one and look.
3. **Lua bytecode variant** — which Lua or LuaJIT build produced it.
4. **Chunk table contents** — the `CrCh` header and table offset are known; the
   chunk types and their payloads are not.
5. **`.wem` codec** — which encoding Wwise used, for the audio re-encode stage.

All five are single-file reads now that extraction is known to work on
everything. None require the whole install.
