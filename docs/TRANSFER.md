# Getting data to the agent

## The short version

**You don't send the game files.** You run a tool where the files already are,
and send back a text block.

If the files are on your phone, everything below happens on your phone. No PC,
no upload, no 41 GB going anywhere.

## Why not just send the files?

Not a rule — arithmetic. 41 GB does not fit in the session container (~30 GB
free), does not fit in Git or LFS, and would be discarded when the container is
reclaimed anyway. Meanwhile the facts worth having weigh a few kilobytes.

The probe measures the install and prints a digest. The digest is what travels.

## On Android, start to finish

Termux gives you a real Python on the phone. The Play Store build is
deprecated — install from **F-Droid** or the project's GitHub releases.

```sh
pkg update && pkg install python git
termux-setup-storage          # grants access to shared storage; approve the prompt

git clone https://github.com/knightdx91-alt/Prey
cd Prey

# Point it at wherever the game files are. termux-setup-storage puts shared
# storage at ~/storage/shared, and /storage/emulated/0 also works.
python3 tools/probe/probe.py ~/storage/shared/Prey -o report.json --digest digest.txt

cat digest.txt

# And the device itself, which is also a project input
pkg install vulkan-tools
python3 tools/device/device.py --digest
```

Copy what `cat` prints. Paste it into the chat. That is the whole transfer.

The tools are standard-library-only Python 3.9+, so Termux needs nothing beyond
`python`. No pip, no build step, no native extensions.

## The channels, by friction

### 1. Paste the digest — best

`--digest` prints a dense text block: histograms, every distinct header
signature, chunk variants, the audio middleware, Lua source-vs-bytecode, and an
explicit list of signatures nothing recognized yet. Typically under 20 KB.

It is capped so it stays pasteable, with one deliberate exception: the
UNRECOGNIZED section is never truncated, because those are the formats nobody
has identified and the reason to send anything at all.

### 2. Commit it to this repo

Useful when you want the findings recorded rather than just read. From a phone
browser, no git or token required:

> github.com/knightdx91-alt/Prey → **Add file** → **Upload files** → pick
> `report.json` → Commit

Then say so, and I will pull and read it. This is the right channel for the
full JSON, which carries more than the digest.

### 3. Google Drive or Gmail

Both connectors are live on this session — verified, not assumed. Upload the
report to Drive or mail it to yourself and say where it is. Plain text and
`.txt` move most reliably; prefer `digest.txt` over `report.json` here.

### 4. A single file, when format work needs real bytes

Sometimes a parser needs the actual bytes. Individual files are small:

```sh
python3 tools/paktool/paktool.py extract "$PAK" -o out/ -p 'Materials/*.mtl'
```

A `.mtl` is a few KB. The first 4 KB of a `.cgf` holds its entire chunk table.
Commit it (`.gitattributes` already routes binary types through LFS) or paste a
hex dump. Whole texture sets and level archives stay where they are.

## What comes back

The digest settles, in one paste:

- whether stock ZIP parsing is enough, and exactly which entries need
  CryPak-aware decoding
- the real extension inventory
- `.cgf`/`.chr` chunk header layout and version numbers — where Arkane's fork
  shows against stock CryEngine
- the audio middleware, from the ATL implementation DLL
- Lua as source or bytecode
- every header signature nothing recognized, as a work queue

That is most of `ASSET_FORMATS.md` promoted from UNVERIFIED in a single step,
and it also feeds `budget.py --report` so the size model stops using assumed
proportions and starts using your install's real mix.

## If Termux is not an option

Any machine with Python 3.9+ works — the install does not have to be on the
same device you chat from, and the tools never write to it. Failing that, say
so and the checks can be narrowed to something a file manager can answer:
directory listings, file sizes, and the first few bytes of a couple of files
still move the format work forward.
