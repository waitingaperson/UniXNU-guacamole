#!/usr/bin/env python3
"""Extract kernelcache, device tree and trust caches from a local IPSW zip.

Mirrors unixnu's ipsw module (BuildManifest lookups + component extraction)
without macOS-only tools: the LZFSE kernelcache is decoded with a local lzfse
binary instead of /usr/bin/compression_tool.
"""
import argparse
import hashlib
import json
import plistlib
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

CHUNK = 1 << 20


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(CHUNK), b''):
            h.update(chunk)
    return h.hexdigest()


def identity(manifest, spec):
    for item in manifest['BuildIdentities']:
        info = item['Info']
        if (info['DeviceClass'] == spec['device_class'] and
                info.get('RestoreBehavior') == 'Erase' and
                int(item['ApChipID'], 16) == int(spec['chip_id']) and
                int(item['ApBoardID'], 16) == int(spec['board_id'])):
            return item
    raise SystemExit('no Erase build identity for this device')


def der(data, at):
    tag, length = data[at], data[at + 1]
    at += 2
    if length & 0x80:
        count = length & 0x7f
        length = int.from_bytes(data[at:at + count], 'big')
        at += count
    return tag, at, length


def im4p_payload(data):
    tag, start, length = der(data, 0)
    if tag != 0x30:
        raise SystemExit('not an IM4P')
    at, items = start, []
    while at < start + length:
        _, body, size = der(data, at)
        items.append(data[body:body + size])
        at = body + size
    if len(items) < 4 or items[0] != b'IM4P':
        raise SystemExit('not an IM4P')
    return items[3]


def extract(zipf, member, cache, pin=None):
    name = Path(member).name
    out = cache / name
    if out.is_file():
        if pin is None or sha256_file(out) == pin:
            return out
        out.unlink()
    cache.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + '.partial')
    with zipf.open(member) as src, tmp.open('wb') as dst:
        for chunk in iter(lambda: src.read(CHUNK), b''):
            dst.write(chunk)
    if pin and sha256_file(tmp) != pin:
        tmp.unlink()
        raise SystemExit(f'{name} does not match the pin {pin}')
    tmp.rename(out)
    print(f'{name}: {out.stat().st_size} bytes sha256 {sha256_file(out)}')
    return out


def decompress_kernelcache(packed, out, lzfse):
    raw = out.with_suffix('.fat')
    subprocess.run([lzfse, '-decode', '-i', str(packed), '-o', str(raw)], check=True)
    fat = raw.read_bytes()
    if fat[:4] == b'\xca\xfe\xba\xbe':
        count = struct.unpack('>I', fat[4:8])[0]
        slices = [struct.unpack('>5I', fat[8 + 20 * i:28 + 20 * i]) for i in range(count)]
        arm64 = [s for s in slices if s[0] == 0x0100000c]
        if len(arm64) != 1:
            raise SystemExit('expected exactly one arm64 slice')
        _, _, offset, size, _ = arm64[0]
        fat = fat[offset:offset + size]
    raw.unlink()
    if fat[:4] != b'\xcf\xfa\xed\xfe':
        raise SystemExit('decompressed kernelcache is not a 64-bit Mach-O')
    out.write_bytes(fat)
    print(f'kernelcache.decompressed: {out.stat().st_size} bytes sha256 {sha256_file(out)}')
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('ipsw')
    parser.add_argument('--board', default='board.toml')
    parser.add_argument('--out', default='out/ipsw')
    parser.add_argument('--lzfse', default='/tmp/lzfse/build/bin/lzfse')
    args = parser.parse_args()

    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib
    board = tomllib.loads(Path(args.board).read_text())
    spec = board['ipsw']
    cache = Path(args.out)
    cache.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(args.ipsw) as zipf:
        manifest = plistlib.loads(zipf.read('BuildManifest.plist'))
        item = identity(manifest, spec)
        manifest_map = item['Manifest']
        for component in spec.get('fetch', ['KernelCache', 'DeviceTree', 'StaticTrustCache']):
            if component not in manifest_map:
                print(f'{component}: not in the manifest')
                continue
            member = manifest_map[component]['Info']['Path']
            pin = spec.get('sha256', {}).get(Path(member).name)
            out = extract(zipf, member, cache, pin)
            if component == 'KernelCache':
                packed = cache / 'kernelcache.im4p'
                packed.write_bytes(im4p_payload(out.read_bytes()))
                target = cache / 'kernelcache.decompressed'
                decompress_kernelcache(packed, target, args.lzfse)
                packed.unlink()
                pin = board['kernel']['prelink'].get('kernelcache_sha256')
                if pin and sha256_file(target) != pin:
                    raise SystemExit(f'the kernelcache does not match board.toml ({sha256_file(target)} != {pin})')
                print('kernelcache pin matches')
    return 0


if __name__ == '__main__':
    sys.exit(main())
