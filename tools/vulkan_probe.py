#!/usr/bin/env python3
"""Report the Vulkan devices visible to the Vulkan loader the SDK uses (criterion C1.4).

ReXGlue's Vulkan Xenos driver refuses a device without these features
(src/gpu/xenos/host/vulkan/vulkan_device.cpp in ReXGlue v0.11.0):
independentBlend, fragmentStoresAndAtomics, vertexPipelineStoresAndAtomics.

The probe runs `vulkaninfo` (vulkan-tools from the same nixpkgs as the SDK), lists every
device with its type and these three features, and exits with:
  0  at least one GPU (not a CPU implementation) has the three features
  3  devices were found, but none is a GPU with the three features
     (for example only a software rasterizer such as lavapipe)
  4  the Vulkan loader found no device (no driver, or no GPU in this environment)
"""

import re
import subprocess
import sys

REQUIRED = ("independentBlend", "fragmentStoresAndAtomics", "vertexPipelineStoresAndAtomics")
GPU_RE = re.compile(r"^GPU(\d+):\s*$")
FEATURE_RE = re.compile(r"^\s+(\w+)\s*=\s*(true|false)\s*$")
FIELD_RE = re.compile(r"^\s+(deviceName|deviceType|apiVersion|driverName|driverInfo)\s*=\s*(.+?)\s*$")


def run(args):
    return subprocess.run(args, capture_output=True, text=True)


def parse_devices(text):
    devices = {}
    current = None
    for line in text.splitlines():
        m = GPU_RE.match(line)
        if m:
            current = devices.setdefault(int(m.group(1)), {"features": {}})
            continue
        if current is None:
            continue
        m = FIELD_RE.match(line)
        if m and m.group(1) not in current:
            current[m.group(1)] = m.group(2)
            continue
        m = FEATURE_RE.match(line)
        if m and m.group(1) in REQUIRED and m.group(1) not in current["features"]:
            current["features"][m.group(1)] = m.group(2) == "true"
    return devices


def main():
    summary = run(["vulkaninfo", "--summary"])
    print("$ vulkaninfo --summary")
    print(summary.stdout.rstrip())
    if summary.stderr.strip():
        print(summary.stderr.rstrip(), file=sys.stderr)
    full = run(["vulkaninfo"])
    devices = parse_devices(full.stdout)
    if full.returncode != 0 or not devices:
        print(f"\nRESULT: no Vulkan device found (vulkaninfo exit status {full.returncode})")
        return 4
    print("\nDevices and the features ReXGlue requires:")
    usable_gpu = False
    for index in sorted(devices):
        d = devices[index]
        kind = d.get("deviceType", "unknown")
        software = "CPU" in kind
        features = d["features"]
        ok = all(features.get(name) is True for name in REQUIRED)
        usable_gpu |= ok and not software
        print(f"  GPU{index}: {d.get('deviceName', '?')} ({kind}), API {d.get('apiVersion', '?')}, "
              f"driver {d.get('driverName', '?')} {d.get('driverInfo', '')}".rstrip())
        for name in REQUIRED:
            value = features.get(name)
            shown = "not reported" if value is None else str(value).lower()
            print(f"    {name} = {shown}")
        print(f"    meets ReXGlue requirements: {'yes' if ok else 'no'}"
              f"{' (software implementation, not a GPU)' if software else ''}")
    if usable_gpu:
        print("\nRESULT: a GPU with the features ReXGlue requires was found")
        return 0
    print("\nRESULT: no GPU with the features ReXGlue requires (only software or unsuitable devices)")
    return 3


if __name__ == "__main__":
    sys.exit(main())
