#!/usr/bin/env python3
"""Build the userdata rootfs image the UniXNU way (docs/zh/guide/userdata).

The image holds the UNCHANGED OS and Cryptex1,SystemOS disk images of the
target IPSW, byte for byte, behind the SHNGROOT manifest:

    0x000000  SHNGROOT manifest, 4096 bytes, zero padding to 1 MiB
    0x100000  window "OS"        the whole OS disk image (GPT + APFS), 1 MiB aligned
    ....      window "SystemOS"  the whole SystemOS cryptex image, 1 MiB aligned

Linux reads the disk images with scripts/local-linux/udif.py (the bytes
`hdiutil attach` would expose); the IPSW members are resolved through the
Restore manifest and checked against board.toml [ipsw.sha256] pins with the
upstream unixnu Ipsw helper. The report (userdata-root.json) records the
window offsets, sizes, hashes, the partition capacity and the flash command.

Nothing is flashed: print the fastboot command for the user to run.
"""
import argparse
import hashlib
import json
import struct
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'unixnu' / 'scripts'))
sys.path.insert(0, str(ROOT / 'scripts' / 'local-linux'))

import udif  # noqa: E402
from unixnu.ipsw import Ipsw  # noqa: E402

MIB = 1 << 20
CHUNK = 8 * MIB


class Context:
    """The slice of the unixnu build context Ipsw needs."""

    def __init__(self, board, out_root):
        self.board = board
        self.out_root = out_root

    def option_text(self, option, env):
        import os
        return os.environ.get(env)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(CHUNK), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--ipsw', help='local (or URL) restore IPSW; default: UNIXNU_IPSW or board.toml [ipsw] url')
    parser.add_argument('--output', default=str(ROOT / 'out/guacamole/userdata/userdata-root.img'))
    parser.add_argument('--dry-run', action='store_true', help='check sizes and the pin match only')
    args = parser.parse_args()

    board = tomllib.loads((ROOT / 'board.toml').read_text())
    spec = board['userdata']
    capacity = (spec['last_lba'] - spec['first_lba'] + 1) * spec.get('lba_bytes', 4096)

    output = Path(args.output)
    out_root = output.parent.parent.parent
    ipsw = Ipsw(Context(board, out_root), args.ipsw or None)
    if args.dry_run:
        for window in spec['windows']:
            name, size, _ = ipsw.info(window['component'])
            print(f'userdata: {window["name"]} would be extracted from {name} ({size >> 20} MiB)')
        print(f'userdata: dry run, capacity {capacity} bytes ({capacity / 2**30:.2f} GiB), nothing extracted or written')
        return
    windows = [(w['name'], ipsw.extract(w['component'])) for w in spec['windows']]

    layout, cursor = [], MIB
    for name, dmg in windows:
        image = udif.Image(dmg)
        layout.append((name, cursor, image.size, image))
        cursor += (image.size + MIB - 1) // MIB * MIB
    total = cursor
    print(f'userdata: image {total} bytes ({total / 2**30:.2f} GiB) '
          f'in a partition of {capacity} bytes ({capacity / 2**30:.2f} GiB)')
    if total > capacity:
        raise SystemExit(f'refusing: the image is larger than the userdata partition')
    for name, offset, size, _ in layout:
        print(f'userdata: window {name} would be {size} bytes at {offset:#x}')
    if args.dry_run:
        print('userdata: dry run, nothing written')
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    with output.open('wb') as target:
        target.truncate(total)
        for name, offset, size, image in layout:
            target.seek(offset)
            digest = hashlib.sha256()
            done = 0
            for block in image.blocks():
                target.write(block)
                digest.update(block)
                done += len(block)
            if done != size:
                raise SystemExit(f'userdata: {name} decoded {done} bytes, not {size}')
            entries.append((name, offset, size, digest.digest()))
            print(f'userdata: {name} {size} bytes at {offset:#x} sha256 {digest.hexdigest()}')
        header = bytearray(4096)
        header[0:8] = b'SHNGROOT'
        struct.pack_into('<IIQ', header, 8, 1, len(entries), total)
        for index, (name, offset, size, digest) in enumerate(entries):
            struct.pack_into('<32sQQII32s40s', header, 24 + 128 * index,
                             name.encode(), offset, size, 512, 1, digest, bytes(40))
        header[4064:4096] = hashlib.sha256(bytes(header[:4064])).digest()
        target.seek(0)
        target.write(header)

    report = {
        'image_bytes': total,
        'image_sha256': sha256_file(output),
        'manifest_sha256': hashlib.sha256(bytes(header)).hexdigest(),
        'windows': [{'name': n, 'offset': o, 'size': s, 'sha256': d.hex()}
                    for n, o, s, d in entries],
        'userdata_bytes': capacity,
        'flash_command': f'fastboot flash userdata {output}',
        'source': 'remote' if ipsw.remote else 'local',
        'hardware_tested': False,
    }
    json_report = output.with_suffix('.json')
    json_report.write_text(json.dumps(report, indent=2) + '\n')
    print(f'userdata: {output}')
    print(f'userdata: report {json_report}')
    print(f'flash it yourself with: {report["flash_command"]}')


if __name__ == '__main__':
    main()
