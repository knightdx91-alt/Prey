# Getting the data

## Can the agent fetch the game itself?

No. Worth being precise about why, because the reason is not the one people
usually assume.

It is **not** a permissions problem — the repository owner's authorization to
reverse-engineer is on file in `CLAUDE.md`. It is a plain access problem:

| Blocker | Detail |
|---|---|
| Storefront auth | Prey is sold through Steam, GOG and Bethesda.net. Downloading requires an account login, and on Steam a Steam Guard second factor. |
| Credentials | An agent should not be handling your storefront account credentials, and you should not paste them into a chat session. This one is a hard line, not an inconvenience. |
| Ephemeral container | The session container is reclaimed after inactivity. A 20+ GB download would not survive to the next session. |
| Size | The install is ~41 GB. The container has ~30 GB free, so it could not be held here regardless. |
| Git is not a game drive | GitHub caps files at 100 MB. Git LFS lifts that but its free tier is ~1 GB of storage and bandwidth. A full install does not fit, and pushing one would be a poor use of the quota regardless. |

Verified in this environment: outbound HTTPS works and `store.steampowered.com`
is reachable, but that yields the *store page*, not the game. GitHub access is
scope-limited to this repository. No game data is present on the container.

## So how does the work actually happen?

The data stays on your machine. Only *facts about* the data travel.

This is not a consolation prize. Nearly every open question in
`ASSET_FORMATS.md` — which compression methods CryPak really uses, what chunk
versions Arkane's fork stamps into `.cgf` files, whether audio is Wwise or
FMOD, whether Lua ships as source or bytecode — is answerable from metadata
measured in kilobytes. The assets themselves are not needed to answer any of
them.

### The loop

```
  your machine                          this repo
  ───────────                           ─────────
  Prey install                          tools/probe/probe.py
       │                                       │
       │  ┌────────────────────────────────────┘
       │  │  1. you run the probe locally
       ▼  ▼
   probe survey  ──── 2. commit or paste (~100s of KB) ────▶  agent reads it
                                                                    │
       ┌──────── 3. VERIFIED facts, better parsers ◀────────────────┘
       ▼
  run the improved tools again
```

1. **You run the probe** against your install. Pure Python 3.9+, standard
   library only, read-only, no install step:

   ```sh
   python3 tools/probe/probe.py "/path/to/Prey" -o prey-report.json
   ```

2. **You share `prey-report.json`.** Commit it, or paste it. It is a few
   hundred KB of counts, histograms and 64-byte header hex dumps. It carries
   no asset content, and it records relative paths only — never the absolute
   install path, which on Windows would contain your account name.

3. **The agent turns it into VERIFIED entries** in `ASSET_FORMATS.md` and uses
   it to write real parsers. Then the loop runs again, deeper each time.

### What one probe run settles immediately

- Whether stock ZIP parsing is enough, and exactly which entries need
  CryPak-aware decoding
- The full extension inventory — what actually ships, versus what CryEngine
  documentation implies should
- `.cgf` / `.chr` chunk header layout and version numbers, which is where the
  Arkane fork diverges from stock CryEngine
- The audio middleware, settled by the ATL implementation DLL's filename
- Lua as source versus bytecode
- Real archive sizes, which feed the Android packaging budget

### When a single file is needed

Format work sometimes needs the bytes. Individual files are small enough to
travel on their own:

```sh
# One material, one mesh header
python3 tools/paktool/paktool.py extract "$PAK" -o out/ -p 'Materials/glass.mtl'
```

A `.mtl` is a few KB of XML. The first 4 KB of a `.cgf` contains its entire
chunk table. Paste a hex dump, or commit the file — `.gitattributes` already
routes the binary types through LFS. Whole texture sets and level archives
should stay where they are.

## What the agent can reach

For completeness, the other inputs available without your install:

- **Public CryEngine source.** Source-available from Crytek and useful as a
  reference for how these formats are *shaped* — though never as ground truth
  for Prey, which runs a fork. GitHub access here is currently scoped to this
  repository; reaching the CryEngine repo needs it attached explicitly.
- **Public format documentation** from the CryEngine modding and RE
  communities.
- **The translation-layer stack** (Box64, Wine, DXVK, Mesa/Turnip) — all open
  source and fetchable, which matters for Phase 2.

## The install size is a separate problem

Prey Digital Deluxe is ~41 GB, and none of it needs to travel — the report is
kilobytes to low megabytes, and deduplicates signatures so it stays flat as the
install grows.

Fitting 41 GB onto a *phone* is a real problem, but a different one. See
`SIZE_BUDGET.md`.

## Summary

The agent cannot obtain Prey, and should not try to. You hold the data; the
repo holds the tools and the findings. The probe is the bridge, and it is
deliberately cheap to cross: one command, one JSON file, no dependencies.
