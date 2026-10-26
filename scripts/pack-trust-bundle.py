#!/usr/bin/env python3
"""Pack Apple's IM4P .trustcache files into the bundle DarwinBoot accepts.

DarwinBoot's ValidTrustCaches (DarwinBootPkg/Driver/DarwinBoot.c) and the
kernel's trust-cache runtime expect:

    u32 module_count (1..128)
    u32 module_offset[module_count]        # start of each module; last ends at EOF
    module = { u32 magic = 2, u8 identifier[16], u32 entries,
               entry[entries] }            # entry = 20B cdhash + 4B (type in 1..4)
    hashes of a module in strictly ascending order (kernel binary search)

The IPSW hands us the same module bytes, but wrapped in an IM4P/DER envelope
(der > IM4P > 'trst' > OCTET STRING payload; lzfse-compressed payloads are
decoded). This unpacks each file, validates the module exactly like the
loader, and concatenates them byte for byte into one bundle. The report
records the module identifiers, entry counts and hashes.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adt import im4p_payload  # noqa: E402


def valid_module(data):
    """The same structural checks as DarwinBoot.c ValidTrustCaches, per module."""
    if len(data) < 24 or struct.unpack_from('<I', data)[0] != 2:
        return f'bad magic: {struct.unpack_from("<I", data)[0]:#x}'
    entries = struct.unpack_from('<I', data, 20)[0]
    if len(data) != 24 + entries * 24:
        return f'size {len(data)} does not match {entries} entries'
    for entry in range(entries):
        at = 24 + entry * 24
        if not 1 <= data[at + 20] <= 4:
            return f'entry {entry}: type byte {data[at + 20]} out of range'
        if entry and data[at - 24:at - 4] >= data[at:at + 20]:
            return f'entry {entry}: hashes not strictly ascending'
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('inputs', nargs='+', help='IM4P .trustcache files (IPSW order)')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()

    modules, report_modules = [], []
    for path in map(Path, args.inputs):
        raw = path.read_bytes()
        payload, info = im4p_payload(raw)
        if info['type'] not in ('trst', 'trcs'):
            raise SystemExit(f'{path.name}: IM4P type {info["type"]!r}, not a trust cache')
        problem = valid_module(payload)
        if problem:
            raise SystemExit(f'{path.name}: module refused by the loader checks: {problem}')
        identifier = payload[4:20].hex()
        entries = struct.unpack_from('<I', payload, 20)[0]
        modules.append(payload)
        report_modules.append({
            'source': path.name,
            'identifier': str(_uuid(identifier)),
            'entries': entries,
            'bytes': len(payload),
            'sha256': hashlib.sha256(payload).hexdigest(),
        })

    header = 4 + 4 * len(modules)
    starts, cursor = [], header
    for module in modules:
        starts.append(cursor)
        cursor += len(module)
    bundle = struct.pack(f'<{1 + len(modules)}I', len(modules), *starts) + b''.join(modules)
    problem = valid_bundle(bundle)
    if problem:
        raise SystemExit(f'internal error, bundle refused: {problem}')

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(bundle)
    report = {
        'bundle_bytes': len(bundle),
        'bundle_sha256': hashlib.sha256(bundle).hexdigest(),
        'modules': report_modules,
    }
    output.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'trust bundle: {output} ({len(bundle)} bytes, {len(modules)} modules)')
    print(f'bundle sha256: {report["bundle_sha256"]}')


def _uuid(identifier_hex):
    import uuid
    raw = bytes.fromhex(identifier_hex)
    return uuid.UUID(bytes=raw)


def valid_bundle(data):
    """Byte-for-byte re-check of the bundle the way DarwinBoot walks it."""
    count = struct.unpack_from('<I', data)[0]
    if not 0 < count <= 128:
        return 'module count out of range'
    for index in range(count):
        start = struct.unpack_from('<I', data, 4 + 4 * index)[0]
        end = struct.unpack_from('<I', data, 8 + 4 * index)[0] if index + 1 < count else len(data)
        if start < 4 + 4 * count or start & 3 or end > len(data) or end - start < 24:
            return f'module {index} bounds'
        if struct.unpack_from('<I', data, start)[0] != 2:
            return f'module {index} magic'
        entries = struct.unpack_from('<I', data, start + 20)[0]
        if end - start != 24 + entries * 24:
            return f'module {index} entry count'
        for entry in range(entries):
            at = start + 24 + entry * 24
            if not 1 <= data[at + 20] <= 4:
                return f'module {index} entry {entry} type'
            if entry and data[at - 24:at - 4] >= data[at:at + 20]:
                return f'module {index} entry {entry} order'
    return None


if __name__ == '__main__':
    main()
