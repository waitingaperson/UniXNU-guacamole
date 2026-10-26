#!/usr/bin/env python3
"""Pack the owner-signed VerifiedRoot policies into the archive NativeUfs links.

Inputs are the policy directories produced by build-owner-policy-linux.py
(build/verified-root-os and build/verified-root-systemos). The documented
pins are enforced so this cannot embed an unverified or substituted image:
the two original restored disks, their exact block counts, and the shared
owner anchor.

The archive layout matches the reference (scripts/build-verified-root-probe.py):
verified_root_manifest/key/samples plus the SystemOS manifest and the
verified_root_policies (manifest, bytes) records consumed by the UFS driver's
multi-policy qualification.
"""
import hashlib
import json
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The guacamole boot partition is 96 MiB, so the policy uses 8 KiB blocks:
# every byte stays covered and the table halves to 22.6 MiB.
OS_PIN = dict(image_sha256='e5634d04a8ac35f024845f583394e0a35deb26a04cb0c00286a8674e25a9a4f2',
              blocks_verified=370947, sample_lengths=[16384, 16384, 16384, 1536])
SYSTEMOS_PIN = dict(image_sha256='b4908cde41d23e6bc05e6af51a2c9eeb00cf0f863a6a18b1600c96a3fd70414f',
                    blocks_verified=201600, sample_lengths=[16384, 16384, 16384, 16384])
OUT = ROOT / 'build/verified-root-xnu'
HEADER_BYTES, SIGNATURE_BYTES = 160, 384


def load(directory, pin):
    directory = Path(directory)
    metadata = json.loads((directory / 'verification.json').read_text())
    key = (directory / 'trusted-key.bin').read_bytes()
    manifest = (directory / 'manifest.bin').read_bytes()
    if (metadata['image_sha256'] != pin['image_sha256'] or metadata['blocks_verified'] != pin['blocks_verified'] or
            not metadata['real_c_signature_and_block_verification'] or
            metadata['actual_sample_lengths'] != pin['sample_lengths'] or
            hashlib.sha256(key).hexdigest() != metadata['trusted_key_sha256']):
        raise SystemExit(f'{directory}: not the fully verified original image')
    image_bytes, count = struct.unpack_from('<QQ', manifest, 24)
    if len(manifest) != HEADER_BYTES + SIGNATURE_BYTES + count * 32 or count != pin['blocks_verified']:
        raise SystemExit(f'{directory}: manifest envelope mismatch')
    return metadata, key, manifest, image_bytes


def main():
    # ShengUfs publishes every window only when all of them authenticate, so
    # both envelopes ride in the kernel (8 KiB blocks keep it under 96 MiB).
    os_meta, key, manifest, os_bytes = load(ROOT / 'build/verified-root-os', OS_PIN)
    sys_meta, sys_key, sys_manifest, sys_bytes = load(ROOT / 'build/verified-root-systemos', SYSTEMOS_PIN)
    if sys_key != key or sys_meta['image_sha256'] == os_meta['image_sha256']:
        raise SystemExit('The two policies must share the owner anchor and describe distinct disks')
    samples = (ROOT / 'build/verified-root-os/original-samples.bin').read_bytes()
    if len(samples) != sum(OS_PIN['sample_lengths']):
        raise SystemExit('sample region does not match the recorded lengths')

    OUT.mkdir(parents=True, exist_ok=True)
    key_file = OUT / 'trusted-key.bin'
    key_file.write_bytes(key)
    assembly = OUT / 'inputs.S'
    assembly.write_text('''// Generated ignored crypto inputs; never a boot-root authorization.
.section __DATA_CONST,__const
.balign 8
.globl _verified_root_manifest, _verified_root_manifest_bytes
_verified_root_manifest:
.incbin "''' + str(ROOT / 'build/verified-root-os/manifest.bin') + '''"
_verified_root_manifest_bytes:
.quad . - _verified_root_manifest
.globl _verified_root_key
_verified_root_key:
.incbin "''' + str(key_file) + '''"
.balign 8
.globl _verified_root_sample_indices
_verified_root_sample_indices:
.quad ''' + ','.join(map(str, os_meta['actual_sample_indices'])) + '''
.globl _verified_root_sample_lengths
_verified_root_sample_lengths:
.quad ''' + ','.join(map(str, OS_PIN['sample_lengths'])) + '''
.globl _verified_root_samples
_verified_root_samples:
.incbin "''' + str(ROOT / 'build/verified-root-os/original-samples.bin') + '''"
.balign 8
.globl _verified_root_systemos_manifest
_verified_root_systemos_manifest:
.incbin "''' + str(ROOT / 'build/verified-root-systemos/manifest.bin') + '''"
.balign 8
.globl _verified_root_policies, _verified_root_policy_count
_verified_root_policies:
.quad _verified_root_manifest, ''' + str(len(manifest)) + '''
.quad _verified_root_systemos_manifest, ''' + str(len(sys_manifest)) + '''
_verified_root_policy_count:
.quad 2
''')

    recipe = ROOT / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/bsd/DEVELOPMENT/bsd_init.o.json'
    record = json.loads(recipe.read_text().strip().rstrip(','))
    objects = []
    for source in (ROOT / 'kits/VerifiedRoot/src/verified_root.c',
                   ROOT / 'kits/VerifiedRoot/adapters/xnu_crypto.c',
                   ROOT / 'scripts/verified-root-probe.c',
                   assembly):
        destination = OUT / (source.stem + '.o')
        compile_args, command, index = record['arguments'], [], 0
        while index < len(compile_args):
            value = compile_args[index]
            if value == record['file']:
                command.append(str(source))
            elif value == '-o':
                command += ['-o', str(destination)]
                index += 1
            elif source.suffix == '.S' and value.startswith('-x'):
                if value == '-x':
                    index += 1
            elif value in ('-MF', '-MJ'):
                index += 1
            elif value == '-MD':
                command += ['-MD']
                index += 1
                if index < len(compile_args) and compile_args[index] == '-dependencies':
                    index += 1
            elif value != '-MP':
                command.append(value)
            index += 1
        command += ['-I' + str(ROOT / 'kits/VerifiedRoot/include'), '-Wno-missing-include-dirs', '-Wno-shadow-header']
        result = subprocess.run(command, cwd=record['directory'], capture_output=True, text=True)
        (OUT / (source.stem + '.log')).write_text(result.stdout + result.stderr)
        if result.returncode:
            raise SystemExit(result.stderr[-3500:])
        data = destination.read_bytes()
        if struct.unpack_from('<4I', data) != (0xfeedfacf, 0x100000c, 0, 1):
            raise SystemExit(f'{source.name}: not a plain ARM64 object')
        cursor, deployment = 32, None
        for _ in range(struct.unpack_from('<I', data, 16)[0]):
            cmd, length = struct.unpack_from('<II', data, cursor)
            if cmd == 0x32:
                deployment = struct.unpack_from('<II', data, cursor + 8)
            cursor += length
        if deployment != (2, 0x110000):
            raise SystemExit(f'{source.name}: not an iOS 17 object')
        objects.append(destination)
    archive = OUT / 'libVerifiedRootProbe.a'
    archive.unlink(missing_ok=True)
    subprocess.run(['xcrun', 'ar', 'rcs', archive, *objects], check=True)
    (OUT / 'inputs.json').write_text(json.dumps(dict(
        manifest_sha256=hashlib.sha256(manifest).hexdigest(),
        manifest_bytes=len(manifest), trusted_key_sha256=hashlib.sha256(key).hexdigest(),
        original_image_sha256=os_meta['image_sha256'], original_block_count=os_meta['blocks_verified'],
        actual_sample_indices=os_meta['actual_sample_indices'],
        actual_sample_lengths=OS_PIN['sample_lengths'],
        systemos_manifest_sha256=hashlib.sha256(sys_manifest).hexdigest(),
        systemos_block_count=sys_meta['blocks_verified'],
        policy_bundle=True, policy_records=2,
        signed_volume_uuid=os_meta['volume_uuid'], signed_systemos_uuid=sys_meta['volume_uuid'],
        archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        boot_root_authenticated=False, test_instrument_only=True), indent=2) + '\n')
    print('PASS: packed owner-signed OS/SystemOS policies into', archive,
          len(manifest) + len(sys_manifest), 'manifest bytes')


if __name__ == '__main__':
    main()
