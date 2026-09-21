#!/usr/bin/env bash
# setup.sh — first-run bootstrap for the Prey Android port tooling.
#
#   ./setup.sh                  device probe only (needs no game files)
#   ./setup.sh /path/to/Prey    device probe + install survey
#
# Installs what is missing, runs the probes, and writes digests you can paste
# back. Safe to re-run; it is idempotent.

set -euo pipefail

BLUE=$'\033[1;34m'; GREEN=$'\033[1;32m'; YELLOW=$'\033[1;33m'; RESET=$'\033[0m'
say()  { printf '%s==>%s %s\n' "$BLUE" "$RESET" "$*"; }
ok()   { printf '%s  ok%s %s\n' "$GREEN" "$RESET" "$*"; }
warn() { printf '%s  !!%s %s\n' "$YELLOW" "$RESET" "$*"; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GAME_PATH="${1:-}"

# --- environment -----------------------------------------------------------

IN_TERMUX=0
[ -n "${PREFIX:-}" ] && case "$PREFIX" in *com.termux*) IN_TERMUX=1 ;; esac

if [ "$IN_TERMUX" -eq 1 ]; then
    say "Termux detected"

    # Shared storage is where a downloaded game is likely to live.
    if [ ! -d "$HOME/storage" ]; then
        say "Requesting storage access (approve the Android prompt)"
        termux-setup-storage || warn "termux-setup-storage failed; continuing"
        sleep 2
    fi

    missing=()
    for pkg_name in python git; do
        command -v "$pkg_name" >/dev/null 2>&1 || missing+=("$pkg_name")
    done
    # vulkan-tools has no binary called "vulkan-tools"; check its payload.
    command -v vulkaninfo >/dev/null 2>&1 || missing+=(vulkan-tools)

    if [ ${#missing[@]} -gt 0 ]; then
        say "Installing: ${missing[*]}"
        pkg install -y "${missing[@]}" || warn "some packages failed to install"
    else
        ok "python, git and vulkaninfo already present"
    fi
else
    say "Not running under Termux — device results will be limited"
fi

PY=python3
command -v python3 >/dev/null 2>&1 || PY=python
command -v "$PY" >/dev/null 2>&1 || { echo "python not found; install it first" >&2; exit 1; }
ok "using $("$PY" -V 2>&1)"

# --- step 1: the device ----------------------------------------------------

say "Probing the device"
"$PY" "$HERE/tools/device/device.py" \
    -o "$HERE/device-report.json" \
    --digest "$HERE/device-digest.txt"
ok "wrote device-digest.txt"

# --- step 2: the install (optional) ----------------------------------------

if [ -n "$GAME_PATH" ]; then
    if [ -d "$GAME_PATH" ]; then
        say "Surveying the install at $GAME_PATH"
        "$PY" "$HERE/tools/probe/probe.py" "$GAME_PATH" \
            -o "$HERE/prey-report.json" \
            --digest "$HERE/prey-digest.txt"
        ok "wrote prey-digest.txt"

        say "Modelling the Android footprint"
        "$PY" "$HERE/tools/budget/budget.py" \
            --report "$HERE/prey-report.json" --all-profiles \
            > "$HERE/budget.txt" 2>&1 || warn "budget model failed"
        ok "wrote budget.txt"
    else
        warn "no such directory: $GAME_PATH — skipping the install survey"
    fi
else
    say "No game path given; skipping the install survey"
    echo "     When you have the files, re-run as: ./setup.sh /path/to/Prey"
fi

# --- output ----------------------------------------------------------------

echo
printf '%s────────── paste everything below this line ──────────%s\n' "$BLUE" "$RESET"
echo
cat "$HERE/device-digest.txt"
if [ -f "$HERE/prey-digest.txt" ]; then
    echo
    cat "$HERE/prey-digest.txt"
fi
echo
printf '%s────────── paste everything above this line ──────────%s\n' "$BLUE" "$RESET"
