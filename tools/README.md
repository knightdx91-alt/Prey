# Tools

Host-side tooling for reading Prey's data. Python 3.9+, standard library only —
no dependencies to install, so these run anywhere a game install can be mounted.

None of these ship game data. They read from a copy you already own.

## probe

Surveys a whole Prey install and writes a single small JSON report. This is the
tool to run **first**, and usually the only one the owner of the data needs to
run by hand.

```sh
# JSON report plus a paste-sized text digest
python3 tools/probe/probe.py "/path/to/Prey" -o report.json --digest digest.txt

# Digest straight to stdout, to copy out of a terminal
python3 tools/probe/probe.py "/path/to/Prey" -o report.json --digest

# Optionally, every entry name across every archive (large, gzipped)
python3 tools/probe/probe.py "/path/to/Prey" -o report.json --listing files.txt.gz
```

`--digest` is the one that matters for getting findings off a phone: a dense
text block, usually under 20 KB, holding the histograms, every distinct header
signature, the chunk variants and an explicit queue of formats nothing
recognized. Signature listing is capped to stay pasteable — except the
UNRECOGNIZED section, which is never truncated, since that is the part worth
carrying back. See `docs/TRANSFER.md`.

It reads the install read-only and records:

- every `.pak`, with entry counts, sizes, and compression-method histograms
- the extension inventory across the whole install
- 64-byte header samples per file type, with known magics identified
- `.cgf`/`.chr` chunk header layout and version numbers
- the audio middleware, inferred from the CryEngine ATL implementation DLL
- Lua source-versus-bytecode counts

**What it does not do:** copy asset content, or record absolute paths. Samples
are capped at 64 bytes — enough for a magic number and a version field, far too
few to constitute a copy of anything. Paths are stored relative to the install
root, because a Windows install path would carry your account name.

The report is a few hundred KB and is meant to be committed or pasted back. See
`docs/GETTING_DATA.md` for why the workflow is shaped this way.

## paktool

Inspects and extracts CryPak (`.pak`) archives.

```sh
# What is in here, and what shape is it?
python3 tools/paktool/paktool.py stats "/path/to/Prey/GameSDK/GameData.pak"

# Names only, or names with sizes and compression methods
python3 tools/paktool/paktool.py list "$PAK"
python3 tools/paktool/paktool.py list "$PAK" -l -p '*.cgf'

# Extract, optionally filtered, optionally rehearsed
python3 tools/paktool/paktool.py extract "$PAK" -o out/
python3 tools/paktool/paktool.py extract "$PAK" -o out/ -p 'Textures/*' -n
```

`stats` is the one to run first against a real install. It reports the
extension histogram and — more usefully — every compression method present,
flagging the ones outside plain store/deflate. Those flagged entries are the
CryEngine-specific codecs, and they are exactly what `docs/ASSET_FORMATS.md`
needs evidence about.

The tool parses the central directory itself rather than deferring to
Python's `zipfile`, so a single undecodable entry costs you that entry and not the
whole archive. It also recovers local-header offsets when data is prepended
ahead of the ZIP structure, which is how a CryPak header would present.

Exit codes: `0` all good, `1` some entries could not be read, `2` the archive
could not be parsed at all.

## budget

Models Prey's Android install footprint. Runs against a probe report for the
real category mix, or against a headline total with assumed proportions when
no report exists yet.

```sh
python3 tools/budget/budget.py --total-gb 41
python3 tools/budget/budget.py --total-gb 41 --all-profiles
python3 tools/budget/budget.py --report prey-report.json --profile aggressive
python3 tools/budget/budget.py --report prey-report.json --json
```

Three profiles — `quality`, `balanced` (default), `aggressive` — each a set of
per-category reduction factors with the reasoning recorded next to the number,
because a factor without its derivation cannot be argued with or corrected.

Every factor is an **estimate** derived from format arithmetic, not from
converting Prey's assets. Replace them with measured ratios once the asset
pipeline exists. See `docs/SIZE_BUDGET.md`.

## device

Reports the Android device's capabilities as they bear on the port. Run under
Termux on the target; needs no root and writes nothing to the device.

```sh
pkg install vulkan-tools          # enables the Vulkan section
python3 tools/device/device.py --digest
python3 tools/device/device.py -o device.json --digest device.txt
```

Reports the GPU family and what it implies for the driver path, Vulkan version
and texture format support (ASTC / BC / ETC2), CPU clusters, RAM, and free
storage checked against every `budget.py` profile.

Facts that cannot be read without root or an app context are reported as
unknown rather than guessed. The GPU family is the decisive one: Adreno has a
mature open Vulkan driver and Xclipse does not, which decides whether Phase 2
is viable. See `docs/DEVICE.md`.

## Tests

```sh
for t in paktool probe budget device; do python3 -m unittest discover -s "tools/$t" -v; done
```

Fixtures are generated at runtime, so the suite needs no game data and commits
no binaries. It covers round-trip integrity, ZIP64, prepended-data offset
recovery, isolation of unsupported codecs, CRC detection of corrupt payloads,
and refusal of path-traversal entries.
