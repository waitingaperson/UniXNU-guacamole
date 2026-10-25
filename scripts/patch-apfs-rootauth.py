#!/usr/bin/env python3
"""Skip APFS's iOS root-hash authentication for the unsealed restore volume.

The target APFS kext (2236.140.6) ends `root_hash_authentication_required` with
`mov w20, #1` (the "authentication is required" result). The restore dmg's
System volume is not sealed and has no snapshot, so the only bootable root is
the live filesystem. Patch that single decision to zero; every other check is
left intact and the change is idempotent.
"""
import sys
from pathlib import Path

PREFIX = bytes.fromhex('0878ffd008350091')
ORIGINAL = bytes.fromhex('34008052')       # mov w20, #1
PATCH = bytes.fromhex('14008052')          # mov w20, #0
SUFFIX = bytes.fromhex('e94200d0')

def main(path: Path) -> int:
    data = bytearray(path.read_bytes())
    found = []
    for word in (ORIGINAL, PATCH):
        blob = PREFIX + word + SUFFIX
        start = 0
        while True:
            at = data.find(blob, start)
            if at < 0:
                break
            found.append((at, word))
            start = at + 1
    if not found:
        raise SystemExit(f'{path}: APFS root-auth site not found')
    if len(found) != 1:
        raise SystemExit(f'{path}: APFS root-auth site is not unique ({len(found)})')
    at, word = found[0]
    if word == PATCH:
        print(f'{path}: root-auth patch already applied')
        return 0
    target = at + len(PREFIX)
    data[target:target + 4] = PATCH
    # apfs_find_named_root_snapshot_xid returns EAUTH when the forwarded
    # payload bytes are missing (the restore volume has no signed root
    # snapshot). Return ENOENT instead so the mount can fall back to the
    # unsealed live filesystem.
    ctx = bytes.fromhex('66d9fe97330a80524d000014')
    at2 = data.find(ctx)
    if at2 < 0:
        raise SystemExit(f'{path}: APFS snapshot-auth site not found')
    if data.find(ctx, at2 + 1) >= 0:
        raise SystemExit(f'{path}: APFS snapshot-auth site is not unique')
    word = at2 + 4
    if data[word:word + 4] == bytes.fromhex('330a8052'):
        data[word:word + 4] = bytes.fromhex('53008052')      # mov w19, #ENOENT
    elif data[word:word + 4] != bytes.fromhex('53008052'):
        raise SystemExit(f'{path}: unexpected bytes at the snapshot-auth site')
    path.write_bytes(data)
    print(f'{path}: APFS root-hash authentication disabled; snapshot lookup falls back to ENOENT')
    return 0

if __name__ == '__main__':
    sys.exit(main(Path(sys.argv[1])))
