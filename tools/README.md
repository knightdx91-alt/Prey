# Tools

Host-side tooling for reading Prey's data. Python 3.9+, standard library only —
no dependencies to install, so these run anywhere a game install can be mounted.

None of these ship game data. They read from a copy you already own.

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
```

Fixtures are generated at runtime, so the suite needs no game data and commits
no binaries. It covers round-trip integrity, ZIP64, prepended-data offset
recovery, isolation of unsupported codecs, CRC detection of corrupt payloads,
and refusal of path-traversal entries.
