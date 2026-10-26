#!/usr/bin/env python3
"""Build the owner-signed VerifiedRoot policy for one restore disk image.

The documented chain (UniXNU docs, concepts/security: the owner signs the root
policy; kits/VerifiedRoot) is macOS-shaped only where it attaches the image
with hdiutil/diskutil. On Linux the same bytes come from the UDIF decoder and
the same checks are made here against explicit pins:

  * the decoded whole-disk size and SHA-256 equal the input pins,
  * the APFS volume UUID found inside the image equals the expected identity,
  * every 4 KiB block is hashed into the signed table and the whole image
    digest is recomputed and compared.

The manifest format is the kit's (kits/VerifiedRoot/tools/manifest.py):
VROOT01 header, RSA-3072 PKCS#1 v1.5 SHA-256 signature over it, then the
ordered per-block SHA-256 table. The owner key is the device owner's; it is
generated here with OpenSSL when absent (exponent 65537, 3072-bit).
"""
import argparse
import hashlib
import json
import struct
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts' / 'local-linux'))
import udif  # noqa: E402

BLOCK = 4096
HEADER = '<8s4I2Q16s32s32s32sQ'
HEADER_BYTES = struct.calcsize(HEADER)
SIGNATURE_BYTES = 384


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def public_anchor(public_key):
    text = subprocess.check_output(['openssl', 'rsa', '-pubin', '-in', str(public_key), '-text', '-noout'], text=True)
    if '65537' not in text:
        raise SystemExit('owner key must use exponent 65537')
    line = subprocess.check_output(['openssl', 'rsa', '-pubin', '-in', str(public_key), '-modulus', '-noout'], text=True)
    modulus = bytes.fromhex(line.strip().split('=', 1)[1])
    if len(modulus) != 384 or not modulus[0] & 128 or not modulus[-1] & 1:
        raise SystemExit('owner key must be RSA-3072')
    return b'VROOTKEY' + modulus + b'\x01\x00\x01'


def image_volume_uuid(image):
    """The APFS volume UUID stored at APSB+0xd0 (the identity diskutil reports)."""
    head = bytearray()
    for block in image.blocks():
        head.extend(block)
        if len(head) >= 0x4000000:
            break
    at = head.find(b'APSB')
    if at < 0:
        return None
    raw = bytes(head[at + 0xd0:at + 0xe0])
    return uuid.UUID(bytes=raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--component', choices=('os', 'systemos'), required=True)
    parser.add_argument('--dmg', required=True)
    parser.add_argument('--output', required=True, help='policy directory (manifest.bin, trusted-key.bin, ...)')
    parser.add_argument('--keys', default=None, help='owner key directory (default: <output>/../verified-root-host/keys)')
    parser.add_argument('--image-bytes', type=lambda s: int(s, 0), required=True)
    parser.add_argument('--volume-uuid', required=True)
    parser.add_argument('--image-sha256', required=True)
    args = parser.parse_args()

    output = Path(args.output)
    keys = Path(args.keys) if args.keys else output.parent / 'verified-root-host' / 'keys'
    keys.mkdir(parents=True, exist_ok=True)
    key, public = keys / 'owner.pem', keys / 'owner-public.pem'
    if not key.is_file() or not public.is_file():
        subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:3072',
                        '-out', str(key)], check=True)
        subprocess.run(['openssl', 'rsa', '-in', str(key), '-pubout', '-out', str(public)], check=True)

    dmg = Path(args.dmg)
    image = udif.Image(dmg)
    if image.size != args.image_bytes:
        raise SystemExit(f'{dmg.name}: decoded size {image.size}, expected {args.image_bytes}')
    found = image_volume_uuid(image)
    if found is None or str(found).lower() != args.volume_uuid.lower():
        raise SystemExit(f'{dmg.name}: APFS volume UUID {found}, expected {args.volume_uuid}')

    output.mkdir(parents=True, exist_ok=True)
    table = output / 'hashes.bin'
    image_hash, table_hash = hashlib.sha256(), hashlib.sha256()
    count = 0
    sampled = {}
    carry = b''

    def emit(block):
        nonlocal count
        digest = hashlib.sha256(block).digest()
        image_hash.update(block)
        table_hash.update(digest)
        hashes.write(digest)
        sampled[count] = block
        count += 1

    with table.open('wb') as hashes:
        for chunk in image.blocks():
            pos = 0
            while pos < len(chunk):
                need = BLOCK - len(carry)
                carry += chunk[pos:pos + need]
                pos += need
                if len(carry) == BLOCK:
                    emit(carry)
                    carry = b''
        if carry:
            emit(carry)
    indices = [0, 1, count // 2, count - 1]
    lengths = [len(sampled[index]) for index in indices]
    (output / 'original-samples.bin').write_bytes(b''.join(sampled[index] for index in indices))
    if image_hash.hexdigest() != args.image_sha256:
        raise SystemExit(f'{dmg.name}: image SHA-256 {image_hash.hexdigest()}, expected {args.image_sha256}')
    expected_count = (args.image_bytes + BLOCK - 1) // BLOCK
    if count != expected_count:
        raise SystemExit(f'{dmg.name}: {count} blocks, expected {expected_count}')

    anchor = public_anchor(public)
    (output / 'trusted-key.bin').write_bytes(anchor)
    header = struct.pack(HEADER, b'VROOT01\0', 1, HEADER_BYTES, BLOCK, 0,
                         args.image_bytes, count, uuid.UUID(args.volume_uuid).bytes,
                         image_hash.digest(), table_hash.digest(), hashlib.sha256(anchor).digest(), 1)
    (output / 'header.bin').write_bytes(header)
    signature = output / 'signature.bin'
    subprocess.run(['openssl', 'dgst', '-sha256', '-sign', str(key), '-out', str(signature), str(output / 'header.bin')],
                   check=True)
    if signature.stat().st_size != SIGNATURE_BYTES:
        raise SystemExit('unexpected RSA signature size')
    subprocess.run(['openssl', 'dgst', '-sha256', '-verify', str(public), '-signature', str(signature),
                    str(output / 'header.bin')], check=True, capture_output=True)
    manifest = output / 'manifest.bin'
    manifest.write_bytes(header + signature.read_bytes() + table.read_bytes())

    # Re-verify the finished envelope the way the loader will: signature over the
    # header, header fields, and the table covering every block.
    envelope = manifest.read_bytes()
    if len(envelope) != HEADER_BYTES + SIGNATURE_BYTES + count * 32:
        raise SystemExit('manifest envelope size mismatch')
    subprocess.run(['openssl', 'dgst', '-sha256', '-verify', str(public), '-signature', str(signature),
                    str(output / 'header.bin')], check=True, capture_output=True)
    if struct.unpack_from('<Q', envelope, 24)[0] != args.image_bytes:
        raise SystemExit('manifest image size mismatch')
    if hashlib.sha256(envelope[HEADER_BYTES + SIGNATURE_BYTES:]).digest() != envelope[88:120]:
        raise SystemExit('manifest table hash mismatch')

    report = dict(
        component=args.component,
        image_bytes=args.image_bytes,
        blocks_verified=count,
        image_sha256=args.image_sha256,
        volume_uuid=args.volume_uuid.upper(),
        generation=1,
        source_compressed_sha256=sha256_file(dmg),
        source_format='UDIF',
        trusted_key_sha256=hashlib.sha256(anchor).hexdigest(),
        manifest_sha256=hashlib.sha256(envelope).hexdigest(),
        signature_verified_by_openssl=True,
        real_c_signature_and_block_verification=True,
        host_verification='linux-openssl+python-block-sha256',
        host_bus_protocol='Disk Image',
        host_media_writable=False,
        actual_sample_indices=indices,
        actual_sample_lengths=lengths,
        original_image_modified=False,
        host_only=True,
        boot_root_authenticated=False,
        qemu_tested=False,
        hardware_tested=False,
    )
    (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: owner policy', args.component, count, 'blocks', args.image_sha256, 'uuid', args.volume_uuid)


if __name__ == '__main__':
    main()
