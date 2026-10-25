#!/usr/bin/env python3
"""Build the SHNGROOT userdata image: the APFS partition of each IPSW disk
image written at a 4K-aligned window, behind a 4 KiB manifest.

The kernel's sweet_ufs driver reads this manifest and exposes the first window
(the OS image's Apple APFS container) as the root block device.
"""
import argparse
import hashlib
import struct
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'local-linux'))
import udif  # noqa: E402

APFS_GUID = '7c3457ef-0000-11aa-aa11-00306543ecac'
MIB = 1 << 20
BLOCK = 4096
SECTOR = 512


def gpt_apfs(dmg):
    """The byte range of the Apple APFS partition inside the DMG's raw disk."""
    image = udif.Image(dmg)
    head = bytearray()
    for block in image.blocks():
        head.extend(block)
        if len(head) >= 1 << 20:
            break
    if head[512:520] != b'EFI PART':
        return 0, image.size
    ent_lba, nent, esz = struct.unpack_from('<QII', head, 512 + 72)
    base = ent_lba * SECTOR
    for i in range(nent):
        at = base + i * esz
        entry = head[at:at + esz]
        if len(entry) < 128 or not any(entry[:16]):
            continue
        import uuid
        if str(uuid.UUID(bytes_le=bytes(entry[:16]))) != APFS_GUID:
            continue
        first, last = struct.unpack_from('<QQ', entry, 32)
        return first * SECTOR, (last - first + 1) * SECTOR
    raise SystemExit(f'{dmg}: no Apple APFS partition in the disk image')


def copy_range(dmg, offset, size, out, digest=None):
    image = udif.Image(dmg)
    pos = 0
    remaining = size
    start = offset
    end = offset + size
    for block in image.blocks():
        block_end = pos + len(block)
        if block_end > start and pos < end:
            lo = max(start, pos) - pos
            hi = min(end, block_end) - pos
            data = block[lo:hi]
            out.write(data)
            if digest is not None:
                digest.update(data)
            remaining -= len(data)
        pos = block_end
        if pos >= end:
            break
    if remaining != 0:
        raise SystemExit(f'{dmg}: short read of the APFS partition')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ipsw', required=True, help='local iPadOS IPSW')
    p.add_argument('--output', required=True)
    p.add_argument('--os', default='044-76040-038.dmg', help='IPSW member holding the OS image')
    p.add_argument('--systemos', default='044-76034-038.dmg', help='IPSW member holding the SystemOS image')
    p.add_argument('--os-name', default='OS')
    p.add_argument('--systemos-name', default='SystemOS')
    args = p.parse_args()

    work = Path(args.output).with_suffix('.src')
    work.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.ipsw) as ipsw:
        members = {name: ipsw.read(name) for name in (args.os, args.systemos)}
    sources = []
    for name, member in ((args.os_name, args.os), (args.systemos_name, args.systemos)):
        path = work / member
        if not path.is_file() or path.stat().st_size != len(members[member]):
            path.write_bytes(members[member])
        offset, size = gpt_apfs(path)
        sources.append((name, path, offset, size))
        print(f'{name}: {member} APFS partition at {offset:#x}, {size} bytes')

    windows, cursor = [], MIB
    for name, path, offset, size in sources:
        windows.append((name, path, offset, size, cursor))
        cursor += (size + MIB - 1) // MIB * MIB
    total = cursor

    entries = []
    with open(args.output, 'wb') as out:
        out.truncate(total)
        for name, path, offset, size, at in windows:
            out.seek(at)
            digest = hashlib.sha256()
            copy_range(path, offset, size, out, digest)
            entries.append((name, at, size, digest.digest()))
            print(f'{name}: wrote {size} bytes at {at:#x} sha256 {digest.hexdigest()}')
        header = bytearray(BLOCK)
        header[0:8] = b'SHNGROOT'
        struct.pack_into('<IIQ', header, 8, 1, len(entries), total)
        for index, (name, at, size, digest) in enumerate(entries):
            struct.pack_into('<32sQQII32s40s', header, 24 + 128 * index,
                             name.encode(), at, size, SECTOR, 1, digest, bytes(40))
        header[BLOCK - 32:] = hashlib.sha256(bytes(header[:BLOCK - 32])).digest()
        out.seek(0)
        out.write(header)
    print(f'image: {args.output} ({total} bytes)')
    print(f'flash: fastboot flash userdata {args.output}')


if __name__ == '__main__':
    main()
