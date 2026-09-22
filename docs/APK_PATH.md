# Getting to an installable APK

Three stages, in order. The first is available now and the third should not
start until the second is done.

## Stage 1 — Home screen shortcut (available today, zero development)

Winlator-class apps can place a shortcut on the Android home screen that
launches a specific container and executable directly. Tap the icon, the game
starts. No container UI, no drive mapping, no Wine desktop.

### How

It is **two steps**, and the second is the one people miss.

**1. Create the shortcut inside Winlator.** Two routes; try the second first if
the Wine desktop is awkward.

*Route A — from Winlator's Shortcuts list.* On the main screen, open the
**Shortcuts** tab and look for a `+` or "Add" control. Some builds let you
browse to an executable directly from there, which skips the Wine desktop
entirely.

*Route B — from the Wine file manager.* Open the file manager on the Wine
desktop, navigate to the mapped drive, and **right-click `Prey.exe`**.

Inside Wine, a long-press is *not* a right-click — the desktop is a real
Windows environment and needs a genuine right mouse button. On touch that is
usually:

| Gesture | Effect |
|---|---|
| **Two-finger tap** | right click (the usual mapping in touchpad mode) |
| One-finger tap | left click |
| Long-press | often nothing, or a drag |

Winlator-class apps generally offer a **touchscreen** and a **touchpad** input
mode, and the gestures differ between them. There may also be an on-screen
control overlay with explicit mouse buttons.

A **Bluetooth or USB mouse** sidesteps all of it and makes the Wine desktop far
easier to work with generally — worth connecting one if available.

**2. Push it to the Android home screen.** Back on Winlator's main screen,
**long-press the shortcut** in the Shortcuts list. That menu should offer "Add
to home screen" (and usually Properties). Confirm, and Android places the icon.

Now tapping that icon launches straight into the game.

### Worth knowing

Shortcuts usually carry **their own settings** — driver, resolution, Box64
options — layered over the container's. That is useful: it means a
configuration can be tuned per game without disturbing the container, and the
shortcut's settings are exactly what Stage 3 would hardcode.

> Menu labels vary between builds and versions. The structure — create from the
> executable, then export to the home screen — is what holds; look for options
> matching that shape rather than those exact words.

**This is a convenience, not a blocker.** The game already launches by
starting the container and running the executable; a shortcut only removes
those taps. If it will not cooperate, skip it — playtime and crash records are
the work that actually matters right now.

**It delivers most of what "an APK I can install" actually means.** It is not
a separate app, but the experience — icon on the home screen, tap to play — is
identical. Worth doing immediately, both because it costs nothing and because
it is the thing to reproduce later in a real APK.

## Stage 2 — Stabilise first

**Do not package an unstable configuration.** An APK built around a build that
crashes produces an app that crashes, plus a build step between every fix and
every test. That is the worst possible iteration loop.

Before packaging:

- [ ] Crashes understood — memory, thermal, or something else
      (see `PHASE2_LOG.md`)
- [ ] A configuration that survives a real play session
- [ ] Settings, driver and container options pinned down and written out

The last point matters most: **the APK is a frozen copy of a container
configuration.** Until that configuration is known and stable, there is nothing
worth freezing.

## Stage 3 — The custom APK

Real Android development, and it belongs on the Windows PC — Android Studio
does not run on Android.

### What it involves

| Step | Notes |
|---|---|
| Fork the Winlator-class app | It is open source; the container runtime is the part being reused |
| Strip the container UI | Remove container management, lists, settings screens |
| Hardcode the configuration | The driver, DXVK version, Box64 options and resolution that Stage 2 established |
| Launcher activity | Boots straight into the executable |
| First-run data flow | Locate or import the 29.3 GiB of game data from external storage |
| Build and sign | Gradle produces a signed APK; sideload to the device |

### What goes where

| Component | Location | Size |
|---|---|---|
| Wine prefix, Box64, DXVK, driver | inside the APK | ~1–2 GB |
| Launcher | inside the APK | trivial |
| Game data | external storage, placed once | 29.3 GiB |

The game does not go in the APK — that was settled in `ROADMAP.md`. The app is
a launcher plus runtime, the same shape emulator frontends use.

### Effort

Days to weeks, depending on prior Android experience. The Gradle and NDK setup
is the fiddly part; the logic is mostly deletion — removing the container UI
from something that already works.

## The honest sequencing

Stage 1 gets the experience today. Stage 2 is the actual current work. Stage 3
is a packaging exercise that becomes straightforward once Stage 2 has produced
something worth packaging — and frustrating if attempted before.
