# Phase 2 — run log

What was tried, and what happened. Append-only; the failures matter as much as
the successes.

---

## 2026-09-22 — installer launches

**Result:** Prey's setup executable runs inside a Winlator container and
renders its UI.

### What this proves

More than it looks like. Getting a Windows installer to display means the
whole lower stack is working:

- Box64 is executing x86-64 code on ARM64
- Wine is servicing Win32 calls well enough for a real installer
- The container's drive mapping resolved
- Basic window presentation reaches the screen

That is most of the translation layer, demonstrated end to end.

### What this does NOT prove

**The 3D path is still completely untested.** Installers draw with plain Win32
GDI — no Vulkan, no DXVK, no shader compilation, no Adreno driver involvement
beyond presenting a window.

Every open question from `PHASE2_SETUP.md` is still open:

- whether the selected driver handles Adreno 840 under real load
- whether DXVK translates CryEngine's D3D11 usage correctly
- whether performance is remotely acceptable
- whether RAM headroom survives the game's working set

The installer is a smoke test for the plumbing. The game is the actual test.

### Immediate risk: install destination

An installer writes a second full copy of the game. With `DEVICE.md`'s measured
**26.64 GB free** and a ~41 GB title, source plus destination does not fit —
the same peak problem `SIZE_BUDGET.md` identified for asset conversion, arriving
earlier than expected.

Two things to get right *before* letting it complete:

1. **Point the destination at the mapped drive, not `C:`.** The container's
   `C:` lives in app private storage. Installing there buries tens of
   gigabytes somewhere awkward to manage and duplicated per container.
2. **Confirm free space against source + destination**, not just destination.

If space is short, an already-installed game folder avoids the problem
entirely — map a drive to it and skip the installer.

### Next

Whether it completes or runs out of room, the useful report is the same: where
it installed to, how much space it consumed, and then what `Prey.exe` itself
does on first launch.

---

## 2026-09-22 — the game runs, then crashes early

**Result:** Prey launches through Winlator, renders 3D gameplay, and reaches
the early suit sequence before crashing.

### What this settles

Phase 2's central question. The full stack carried a CryEngine deferred
renderer on a phone:

- Box64 executing x86-64 game code on ARM64
- Wine servicing Win32 at gameplay scale, not just an installer
- DXVK translating Prey's D3D11 usage to Vulkan
- The Adreno 840 driver running the result

Every risk flagged in `PHASE2_SETUP.md` about whether the driver, DXVK or
CryEngine's renderer would cooperate is now answered: they do. The translation
layer is viable, not speculative.

That promotes the project from "might be possible" to "demonstrably runs, and
the work is now stability and performance."

### What it does not settle

It reached an early scripted sequence, not a play session. Still unknown:
frame rate under sustained load, thermal behaviour past ten minutes, whether
later and heavier areas load at all, and whether the crash is a one-off or the
first of many.

### The crash — triage

Not diagnosed. The single most useful fact is not yet known:

> **Does it crash at the same point every time?**

That splits the diagnosis cleanly:

| Reproducible at the same point | Non-deterministic |
|---|---|
| A specific shader DXVK cannot compile | RAM exhaustion |
| A specific asset or effect | Thermal throttling / timing |
| A missing Vulkan feature path | Driver instability under load |
| A scripted-sequence code path | Background app eviction |

**RAM is the leading suspect if it is non-deterministic.** `DEVICE.md` measured
10.83 GB total with ~3.09 GB actually free, against a game that expects 8 GB+
on desktop. A streaming spike during a scripted sequence is exactly where that
would bite.

### What to gather next

1. **Reproduce it.** Same save, same action, three times. Same point or not?
2. **Capture the log.** Winlator keeps Wine's output; `DXVK_LOG_LEVEL=info`
   adds shader and device detail. The last lines before the crash usually name
   the subsystem.
3. **Cut memory pressure.** Close everything else, drop resolution and texture
   quality, retry. If the crash moves or disappears, it is memory.
4. **Change only the driver.** If it is deterministic and survives a driver
   swap, it is the game or DXVK; if it moves, it is the driver.

One variable at a time. A crash that reproduces on demand is a tractable bug;
the aim of this round is to make it reproduce on demand.

---

## 2026-09-22 — same sequence, no crash

**Result:** Repeated the suit sequence. It did not crash.

### What this narrows

The crash is **not reliably reproducible at that point**, which is evidence
against the deterministic causes and toward the stateful ones:

| Now less likely | Now more likely |
|---|---|
| A shader DXVK cannot compile | **RAM exhaustion** |
| A specific asset or effect | Thermal throttling |
| A missing Vulkan feature path | Driver instability under load |
| A scripted-sequence code path | Background app eviction |

Stated precisely: one clean pass shows it is not *consistently* deterministic.
It does not prove randomness — a state-dependent trigger would also survive one
retry. But the leading hypothesis has moved.

### Why memory leads

`DEVICE.md` measured 10.83 GB total with **~3.09 GB actually free**, against a
game that expects 8 GB+ on desktop. Add Wine, Box64 and DXVK's own overhead on
top of Prey's working set. A crash that comes and goes at the same story point
is exactly the shape of an allocation failing when the device happens to be
under more pressure — a different set of background apps resident, a warmer
device, a slightly different streaming order.

### The strategic consequence

If memory is the cause, **Phase 3 stops being only a size optimisation and
becomes the stability fix.** Lower-resolution textures cut the streaming
footprint directly. That reorders the project: the asset pipeline earns its
place sooner than "make the install smaller" implied.

That connection is worth confirming before acting on it.

### Accumulate a pattern

A single crash is an anecdote. Record each one and the shape emerges:

| Field | Why |
|---|---|
| Minutes into the session | Separates early failures from heat-soak failures |
| Where / what was happening | Finds asset-load correlation |
| Device warm or cool | Thermal signal |
| Other apps open beforehand | Memory-pressure signal |
| Settings in use | Lets a change be attributed |

Four or five entries should distinguish memory from thermals: memory-driven
crashes cluster around heavy loads regardless of elapsed time, thermal ones
cluster after sustained play.

### Worth trying now

CryEngine exposes texture streaming budgets as console variables —
`r_TexturesStreamPoolSize` is the relevant one, sized in MB, and is typically
settable from a `system.cfg` beside the executable. Whether Prey honours it is
unverified and cheap to test.

Lowering it trades texture pop-in for a smaller resident footprint, which is
the correct trade here. If crash frequency drops, that both confirms the
memory hypothesis and buys stability before the asset pipeline exists.
