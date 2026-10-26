#!/usr/bin/env python3
"""UniXNU ADT step for guacamole.

The UniXNU payload driver passes the generic ADT flags (chip-id,
owned-memory-size, root-match UUID, CPU registers, PSCI method, trust cache,
...). The guacamole hardware profile in mkadt.py owns those values; accept the
flags and generate the D22AP/guacamole tree with the requested DRAM size.
"""
import argparse
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--output", required=True)
    parser.add_argument("--dram-size", default="0xc0000000")
    parser.add_argument("--owned-memory-size", type=lambda value: int(value, 0))
    parser.add_argument("--ipad-identity", action="store_true")
    parser.add_argument("--chip-id")
    parser.add_argument("--root-match-volume-uuid")
    parser.add_argument("--trust-cache", action="store_true")
    parser.add_argument("--data-ramdisk", action="store_true")
    parser.add_argument("--packed-data-ramdisk", action="store_true")
    parser.add_argument("--persistent-data", action="store_true")
    known, _unknown = parser.parse_known_args()
    tool = Path(__file__).resolve().parent / "mkadt.py"
    command = [sys.executable, str(tool), known.output, "--device", "guacamole",
               "--dram-size", known.dram_size]
    if known.owned_memory_size is not None:
        command += ["--owned-memory-size", str(known.owned_memory_size)]
    if known.ipad_identity:
        command.append("--ipad-identity")
    if known.chip_id:
        command += ["--chip-id", str(known.chip_id)]
    if known.root_match_volume_uuid:
        command += ["--root-match-volume-uuid", known.root_match_volume_uuid]
    if known.trust_cache:
        command += ["--trust-cache"]
    if known.data_ramdisk:
        command += ["--data-ramdisk"]
    if known.packed_data_ramdisk:
        command += ["--packed-data-ramdisk"]
    if known.persistent_data:
        command += ["--persistent-data"]
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
