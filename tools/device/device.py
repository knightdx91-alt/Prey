#!/usr/bin/env python3
"""device — report the Android device's capabilities as they bear on the port.

When the phone is both the development machine and the target, its limits stop
being trivia and become project constraints: the GPU decides the driver path,
the supported texture formats decide the asset pipeline, free storage decides
whether the budget in docs/SIZE_BUDGET.md is reachable at all.

Run under Termux. Nothing here needs root, and nothing is written to the
device. Where a fact cannot be read without root or an app context, it is
reported as unknown rather than guessed -- an unknown is useful, an invented
number is not.

    python3 tools/device/device.py
    python3 tools/device/device.py -o device.json --digest
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from typing import Any

# Android system properties worth having, grouped by what they decide.
PROPS: dict[str, tuple[str, ...]] = {
    "identity": (
        "ro.product.manufacturer", "ro.product.model", "ro.product.device",
        "ro.product.name",
    ),
    "os": (
        "ro.build.version.release", "ro.build.version.sdk",
        "ro.build.version.security_patch",
    ),
    "cpu": (
        "ro.product.cpu.abi", "ro.product.cpu.abilist", "ro.board.platform",
        "ro.soc.manufacturer", "ro.soc.model", "ro.hardware",
    ),
    "graphics": (
        "ro.hardware.egl", "ro.hardware.vulkan", "ro.opengles.version",
        "ro.gfx.driver.0", "ro.surface_flinger.supports_background_blur",
    ),
    "memory": (
        "dalvik.vm.heapsize", "dalvik.vm.heapgrowthlimit", "dalvik.vm.heapstartsize",
    ),
    "display": ("ro.sf.lcd_density",),
}

# GPU families and the driver story each implies for a translation layer.
GPU_NOTES: dict[str, str] = {
    "adreno": "Adreno — Mesa/Turnip is the mature open Vulkan path; best case "
              "for a DXVK-style stack.",
    "mali": "Mali — Panfrost/PanVk is less mature for recent parts; expect "
            "the vendor Vulkan driver to be the only viable route.",
    "powervr": "PowerVR — limited open driver support.",
    "xclipse": "Xclipse (AMD RDNA-derived, Samsung Exynos) — vendor Vulkan "
               "driver only; no mature open path.",
}

# Samsung region suffixes. These encode naming convention, not hardware specs:
# the suffix says which regional variant a unit is, and US variants of Samsung
# flagships have consistently shipped Qualcomm parts (hence Adreno) even in
# generations where other regions got Exynos (hence Xclipse). Useful as a prior
# when vulkaninfo is not installed; the probe still confirms from the driver.
SAMSUNG_REGIONS = {
    "U": ("US carrier/unlocked", "Snapdragon expected -> Adreno"),
    "U1": ("US unlocked", "Snapdragon expected -> Adreno"),
    "B": ("Europe / international", "varies by generation; confirm"),
    "N": ("Korea", "varies by generation; confirm"),
    "W": ("Canada", "varies by generation; confirm"),
    "0": ("open market", "varies by generation; confirm"),
}


def decode_samsung_model(model: str) -> dict[str, Any] | None:
    """Decode a Samsung model number into family and regional variant.

    This reads a naming convention, not a spec sheet. It yields a prior about
    the likely SoC vendor, which the Vulkan driver then confirms or overturns.
    """
    match = re.match(r"^SM-([A-Z])(\d{3})([A-Z]\d?|\d)?$", model.strip().upper())
    if not match:
        return None
    series, number, suffix = match.group(1), match.group(2), match.group(3) or ""

    families = {"F": "Galaxy Z (foldable)", "S": "Galaxy S", "G": "Galaxy S (older)",
                "N": "Galaxy Note", "A": "Galaxy A", "T": "Galaxy Tab"}
    info: dict[str, Any] = {
        "model": model.strip().upper(),
        "family": families.get(series, f"unknown series {series}"),
        "number": number,
    }
    if series == "F" and number.startswith("9"):
        info["family"] = "Galaxy Z Fold"
    if suffix:
        region, soc = SAMSUNG_REGIONS.get(suffix, ("unrecognized suffix", "confirm"))
        info["region"] = region
        info["soc_prior"] = soc
    return info


# Software Vulkan implementations. Under Termux these load in place of the
# vendor driver, and their capabilities are the CPU's, not the GPU's. Reporting
# them as the device's is worse than reporting nothing, because it looks like a
# measurement -- so they are detected and flagged rather than trusted.
SOFTWARE_RENDERERS = ("llvmpipe", "lavapipe", "swiftshader", "softpipe")

# Desktop install size, and the modelled Android outputs from
# docs/SIZE_BUDGET.md. Both are estimates; see that document.
SOURCE_GB = 41.0
BUDGET_PROFILES = (("aggressive", 6.7), ("balanced", 9.5), ("quality", 20.9))

# Where Android keeps the vendor Vulkan driver. Termux can usually stat these
# even when it cannot load them, which is enough to confirm the real driver
# exists and name it.
VENDOR_VULKAN_DIRS = (
    "/vendor/lib64/hw", "/vendor/lib/hw", "/system/lib64/hw", "/system/lib/hw",
)


def find_vendor_vulkan() -> list[str]:
    """Locate the hardware Vulkan drivers present on the device."""
    found = []
    for directory in VENDOR_VULKAN_DIRS:
        try:
            for name in sorted(os.listdir(directory)):
                if name.startswith("vulkan.") and name.endswith(".so"):
                    found.append(f"{directory}/{name}")
        except OSError:
            continue
    return found


def is_software_renderer(name: str) -> bool:
    lowered = (name or "").lower()
    return any(marker in lowered for marker in SOFTWARE_RENDERERS)


# OpenGL ES version property is an encoded integer: 0xMMMMmmmm.
def decode_gles(value: str) -> str | None:
    try:
        raw = int(value)
    except (TypeError, ValueError):
        return None
    return f"{raw >> 16}.{raw & 0xFFFF}"


def run(cmd: list[str], timeout: int = 20) -> str | None:
    """Run a command, returning its stdout, or None if it is unavailable."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 and not result.stdout:
        return None
    return result.stdout


def read_props() -> dict[str, dict[str, str]]:
    """Read Android system properties via getprop, grouped."""
    out: dict[str, dict[str, str]] = {}
    if shutil.which("getprop") is None:
        return out

    # One getprop call returns everything; parsing it beats N subprocesses.
    dump = run(["getprop"])
    table: dict[str, str] = {}
    if dump:
        for line in dump.splitlines():
            match = re.match(r"\[([^\]]+)\]:\s*\[(.*)\]$", line.strip())
            if match:
                table[match.group(1)] = match.group(2)

    for group, keys in PROPS.items():
        values = {k: table[k] for k in keys if table.get(k)}
        if values:
            out[group] = values
    return out


def read_meminfo() -> dict[str, Any]:
    info: dict[str, Any] = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                key, _, rest = line.partition(":")
                if key in ("MemTotal", "MemAvailable", "SwapTotal"):
                    parts = rest.split()
                    if parts and parts[0].isdigit():
                        info[key] = int(parts[0]) * 1024
    except OSError:
        pass
    return info


def read_cpu() -> dict[str, Any]:
    """CPU topology. Android restricts /proc/cpuinfo detail, so this is partial."""
    info: dict[str, Any] = {"cores": os.cpu_count()}
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return info

    parts = sorted(set(re.findall(r"CPU part\s*:\s*(\S+)", text)))
    if parts:
        info["cpu_parts"] = parts
    hardware = re.search(r"Hardware\s*:\s*(.+)", text)
    if hardware:
        info["hardware"] = hardware.group(1).strip()

    # Max clock per core, where the kernel exposes it.
    freqs = []
    for cpu in range(info["cores"] or 0):
        path = f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/cpuinfo_max_freq"
        try:
            with open(path, encoding="utf-8") as fh:
                freqs.append(int(fh.read().strip()) // 1000)
        except (OSError, ValueError):
            break
    if freqs:
        info["max_mhz_per_core"] = freqs
        info["core_clusters"] = sorted(set(freqs), reverse=True)
    return info


def read_storage() -> list[dict[str, Any]]:
    """Free space on the paths that matter for a multi-gigabyte install."""
    candidates = [
        ("home", os.path.expanduser("~")),
        ("shared", os.path.expanduser("~/storage/shared")),
        ("emulated", "/storage/emulated/0"),
        ("data", "/data"),
    ]
    seen: set[tuple[int, int]] = set()
    out = []
    for label, path in candidates:
        if not os.path.isdir(path):
            continue
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            continue
        key = (usage.total, usage.free)
        if key in seen:  # same filesystem under another name
            continue
        seen.add(key)
        out.append({
            "label": label, "path": path,
            "total": usage.total, "free": usage.free,
        })
    return out


def read_vulkan() -> dict[str, Any]:
    """Vulkan capabilities via vulkaninfo, if the package is installed."""
    if shutil.which("vulkaninfo") is None:
        return {
            "available": False,
            "hint": "pkg install vulkan-tools  (Termux) to enable this section",
        }

    text = run(["vulkaninfo", "--summary"], timeout=60) or run(["vulkaninfo"], timeout=90)
    if not text:
        return {"available": False, "error": "vulkaninfo produced no output"}

    info: dict[str, Any] = {"available": True}
    for key, pattern in (
        ("api_version", r"apiVersion\s*=\s*([\w.]+)"),
        ("driver_version", r"driverVersion\s*=\s*([\w.]+)"),
        ("device_name", r"deviceName\s*=\s*(.+)"),
        ("device_type", r"deviceType\s*=\s*(\S+)"),
        ("driver_name", r"driverName\s*=\s*(.+)"),
    ):
        match = re.search(pattern, text)
        if match:
            info[key] = match.group(1).strip()

    # Texture format support decides the asset pipeline outright -- but only if
    # it came from the real driver.
    lowered = text.lower()
    info["astc_ldr"] = "textureCompressionASTC_LDR".lower() in lowered
    info["astc_hdr"] = "textureCompressionASTC_HDR".lower() in lowered
    info["bc"] = "texturecompressionbc" in lowered
    info["etc2"] = "texturecompressionetc2" in lowered

    info["software"] = is_software_renderer(info.get("device_name", ""))
    if info["software"]:
        info["warning"] = (
            "This is a SOFTWARE rasterizer, not the GPU. Every capability above "
            "describes the CPU fallback. Texture format results are meaningless "
            "for this device -- re-measure with a native Android Vulkan app."
        )
        info["vendor_drivers"] = find_vendor_vulkan()
    return info


def classify_gpu(props: dict[str, dict[str, str]], vulkan: dict[str, Any]) -> dict[str, Any]:
    """Name the GPU family and what it implies for the driver path."""
    haystack = " ".join([
        vulkan.get("device_name", ""),
        props.get("graphics", {}).get("ro.hardware.egl", ""),
        props.get("cpu", {}).get("ro.board.platform", ""),
        props.get("cpu", {}).get("ro.soc.model", ""),
    ]).lower()

    for family, note in GPU_NOTES.items():
        if family in haystack:
            return {"family": family, "note": note}
    return {
        "family": "unknown",
        "note": "GPU family not identified; install vulkan-tools so deviceName "
                "can be read.",
    }


def collect() -> dict[str, Any]:
    props = read_props()
    vulkan = read_vulkan()
    gles = props.get("graphics", {}).get("ro.opengles.version")

    model = props.get("identity", {}).get("ro.product.model", "")
    decoded = decode_samsung_model(model) if model else None

    report: dict[str, Any] = {
        "model_decoded": decoded,
        "is_android": bool(props) or "ANDROID_ROOT" in os.environ,
        "in_termux": "com.termux" in os.environ.get("PREFIX", ""),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "properties": props,
        "cpu": read_cpu(),
        "memory": read_meminfo(),
        "storage": read_storage(),
        "vulkan": vulkan,
        "gpu": classify_gpu(props, vulkan),
    }
    if gles:
        report["opengl_es"] = decode_gles(gles)
    return report


def _size(n: float) -> str:
    for unit, scale in (("GB", 1024 ** 3), ("MB", 1024 ** 2), ("KB", 1024)):
        if n >= scale:
            return f"{n / scale:.2f} {unit}"
    return f"{n:.0f} B"


def digest(report: dict[str, Any]) -> str:
    out: list[str] = []
    add = out.append
    ident = report["properties"].get("identity", {})
    cpu_props = report["properties"].get("cpu", {})

    add("PREY DEVICE DIGEST v1")
    if not report["is_android"]:
        add("NOT ANDROID — run this under Termux on the target device")
    add(f"model={ident.get('ro.product.model', '?')} "
        f"vendor={ident.get('ro.product.manufacturer', '?')} "
        f"device={ident.get('ro.product.device', '?')}")

    os_props = report["properties"].get("os", {})
    add(f"android={os_props.get('ro.build.version.release', '?')} "
        f"sdk={os_props.get('ro.build.version.sdk', '?')} "
        f"abi={cpu_props.get('ro.product.cpu.abi', report['machine'])}")
    add(f"soc={cpu_props.get('ro.soc.model', '?')} "
        f"platform={cpu_props.get('ro.board.platform', '?')}")

    cpu = report["cpu"]
    add(f"cores={cpu.get('cores', '?')} "
        f"clusters={cpu.get('core_clusters', 'unknown')}")

    mem = report["memory"]
    if mem.get("MemTotal"):
        add(f"ram={_size(mem['MemTotal'])} available={_size(mem.get('MemAvailable', 0))}")

    decoded = report.get("model_decoded")
    if decoded:
        add(f"family={decoded.get('family', '?')} "
            f"region={decoded.get('region', '?')}")
        if decoded.get("soc_prior"):
            add(f"soc_prior={decoded['soc_prior']}  (prior only; driver confirms)")

    add(f"gpu_family={report['gpu']['family']}")
    if report.get("opengl_es"):
        add(f"opengl_es={report['opengl_es']}")

    vk = report["vulkan"]
    if vk.get("available") and vk.get("software"):
        add(f"vulkan=SOFTWARE-ONLY device={vk.get('device_name', '?')}")
        add("  !! NOT THE GPU — this is a CPU rasterizer loaded by Termux.")
        add("  !! Texture format support below is the CPU's and means nothing here.")
        add(f"  (reported anyway) astc_ldr={vk.get('astc_ldr')} "
            f"bc={vk.get('bc')} etc2={vk.get('etc2')}")
        for driver in vk.get("vendor_drivers", []):
            add(f"  hardware driver present: {driver}")
        if not vk.get("vendor_drivers"):
            add("  no vendor vulkan.*.so found in the usual paths")
    elif vk.get("available"):
        add(f"vulkan={vk.get('api_version', '?')} device={vk.get('device_name', '?')}")
        add(f"astc_ldr={vk.get('astc_ldr')} astc_hdr={vk.get('astc_hdr')} "
            f"bc={vk.get('bc')} etc2={vk.get('etc2')}")
    else:
        add(f"vulkan=UNAVAILABLE  ({vk.get('hint') or vk.get('error', '')})")

    add("")
    add("STORAGE")
    for entry in report["storage"]:
        add(f"  {entry['label']:<10} free={_size(entry['free']):>10} "
            f"total={_size(entry['total']):>10}  {entry['path']}")

    add("")
    add("BUDGET CHECK (docs/SIZE_BUDGET.md)")
    best = max((e["free"] for e in report["storage"]), default=0)
    add(f"  free now {_size(best)}")
    add("  converted output alone:")
    for label, need_gb in BUDGET_PROFILES:
        need = need_gb * 1024 ** 3
        verdict = "fits" if best >= need else f"short by {_size(need - best)}"
        add(f"    {label:<12} {need_gb:>5.1f} GB   {verdict}")

    # Converting needs the source install present at the same time as its
    # output, so the peak is the sum -- which is the number that actually
    # decides whether the pipeline can run on-device.
    add(f"  during conversion (source {SOURCE_GB:.0f} GB + output):")
    for label, need_gb in BUDGET_PROFILES:
        peak = (SOURCE_GB + need_gb) * 1024 ** 3
        verdict = "fits" if best >= peak else f"short by {_size(peak - best)}"
        add(f"    {label:<12} {SOURCE_GB + need_gb:>5.1f} GB   {verdict}")

    add("")
    add("END DIGEST")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="device",
        description="Report Android device capabilities relevant to the port.",
    )
    parser.add_argument("-o", "--output", help="write the full JSON report here")
    parser.add_argument(
        "--digest", nargs="?", const="-", metavar="FILE",
        help="write a paste-sized digest (default: stdout)",
    )
    args = parser.parse_args(argv)

    report = collect()

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        print(f"report -> {args.output}", file=sys.stderr)

    text = digest(report)
    if args.digest and args.digest != "-":
        with open(args.digest, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"digest -> {args.digest}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
