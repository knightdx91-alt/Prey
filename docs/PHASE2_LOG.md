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
