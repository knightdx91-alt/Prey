# Tools

Host-side tooling for reading Prey's data. Python 3.9+, standard library only —
no dependencies to install, so these run anywhere a game install can be mounted.

None of these ship game data. They read from a copy you already own.

## probe

Surveys a whole Prey install and writes a single small JSON report. This is the
tool to run **first**, and usually the only one the owner of the data needs to
run by hand.

```sh
python3 tools/probe/probe.py "/path/to/Prey" -o prey-report.json

# Optionally, every entry name across every archive (large, gzipped)
python3 tools/probe/probe.py "/path/to/Prey" -o prey-report.json --listing files.txt.gz
```

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

## Tests

```sh
python3 -m unittest discover -s tools/paktool -v
python3 -m unittest discover -s tools/probe -v
```

Fixtures are generated at runtime, so the suite needs no game data and commits
no binaries. It covers round-trip integrity, ZIP64, prepended-data offset
recovery, isolation of unsupported codecs, CRC detection of corrupt payloads,
and refusal of path-traversal entries.
