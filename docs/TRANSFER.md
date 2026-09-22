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
pkg install -y git
git clone https://github.com/knightdx91-alt/Prey
cd Prey
./setup.sh
```

`setup.sh` installs what is missing, requests storage access, probes the
device, and prints a digest between two marker lines. Copy everything between
them and paste it into the chat. That is the whole transfer.

> **Expected noise on first install.** Termux's `git` package depends on
> `openssh`, so installing it generates three sshd host keys and prints their
> fingerprints and randomart. That is normal and needs no action. The
> fingerprints are public by design — they identify a server, they are not
> secrets. Termux then suggests enabling the `sshd` and `ssh-agent` services;
> **nothing here needs either**, so skip that unless you want SSH into the
> phone for your own reasons.

It needs no game files — the device half is useful on its own, and answers the
question that gates Phase 2.

When the game is on the device, re-run with its path. Shared storage lands at
`~/storage/shared`, and `/storage/emulated/0` works too:

```sh
./setup.sh ~/storage/shared/Prey
```

That adds the install survey and the footprint model to the same output.

### Doing it by hand

`setup.sh` is only a wrapper. The individual tools work directly:

```sh
python3 tools/device/device.py --digest
python3 tools/probe/probe.py ~/storage/shared/Prey -o report.json --digest digest.txt
```

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
- a provenance verdict: whether the archives were all written by one tool, which
  decides how much weight archive-layout claims can carry (see
  `ASSET_FORMATS.md`). Content facts are unaffected either way.

That is most of `ASSET_FORMATS.md` promoted from UNVERIFIED in a single step,
and it also feeds `budget.py --report` so the size model stops using assumed
proportions and starts using your install's real mix.

## When the game is on a PC

This is the better situation, and it changes the order of operations.

### Run the probe there first

A laptop has real Python, a fast CPU and no Termux quirks. Ten minutes there
produces what the phone cannot easily:

```sh
python3 tools/probe/probe.py "C:/path/to/Prey" -o report.json --digest digest.txt
python3 tools/budget/budget.py --report report.json --all-profiles
```

That does three things at once:

1. **Unblocks Phase 1.** Every UNVERIFIED entry in `ASSET_FORMATS.md` becomes
   answerable — compression methods, chunk versions, the audio middleware, Lua
   encoding.
2. **Replaces the assumed size split** with the install's real category mix, so
   the footprint model stops guessing.
3. **Tells you what is safe to leave behind.** The extension and archive
   inventory shows where the gigabytes actually are. Optional language packs
   and similar are usually several GB and usually unnecessary.

Point 3 matters immediately: the device has **26.64 GB free** against a ~41 GB
title. Something has to give, and knowing *what* beats deleting blindly.

### Then copy the installed folder, not an installer

Copying an already-installed tree is strictly better than running setup inside
a container:

- **One copy, not two.** An installer needs source and destination resident at
  once — roughly 82 GB for a 41 GB game. A straight copy needs 41.
- **No installer compatibility risk.** Wine running a game is one problem;
  Wine running an installer is a second, unrelated one. Skip it.
- **It is the shape the drive-mapping approach wants** anyway.

### Getting 41 GB across

| Method | Notes |
|---|---|
| `adb push` | Reliable for large transfers; needs USB debugging enabled |
| Network (SMB / FTP / rsync over wifi) | Often faster and more robust than USB MTP |
| USB-C file transfer | Works, but MTP handles very large trees poorly |

Prefer something resumable. A 41 GB transfer that fails at 90% over MTP with
no resume is a bad evening.

### Watch for a storefront dependency

If the install came from a storefront, the executable may expect that client to
be running. That is a separate problem from the game itself and a common first
failure under Wine — worth knowing before concluding the translation layer is
at fault.

## If Termux is not an option

Any machine with Python 3.9+ works — the install does not have to be on the
same device you chat from, and the tools never write to it. Failing that, say
so and the checks can be narrowed to something a file manager can answer:
directory listings, file sizes, and the first few bytes of a couple of files
still move the format work forward.
