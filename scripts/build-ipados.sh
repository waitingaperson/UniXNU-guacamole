#!/bin/bash
# Prelink the 10063 kernel against the iPadOS 17.7.11 kernelcache and pack it.
set -euo pipefail
cd "$(dirname "$0")/.."
KERNEL=${1:?usage: build-ipados.sh <unstripped kernel>}
KERNELCACHE=out/ipsw/kernelcache.decompressed
TRUSTCACHE=${TRUSTCACHE:-out/ipsw/044-76040-038.dmg.trustcache}
OUT=out/guacamole/kernel/kernel-ipados-17711-prelinked.macho

roots=()
while IFS= read -r root; do roots+=(--root "$root"); done < <(python3 - <<'PY'
import tomllib
b = tomllib.loads(open('board.toml').read())
for r in b['kernel']['prelink']['roots']:
    print(r)
PY
)

rm -f "$OUT" "${OUT%.macho}.json"
python3 unixnu/kits/NativePrelink/emit_prelink.py \
  --kernel "$KERNEL" \
  --prelinked "$KERNELCACHE" \
  --slide=-0x1000000 \
  --early-security-init "com.apple.driver.AppleMobileFileIntegrity=0xfffffff005ab4ae0" \
  --output "$OUT" \
  "${roots[@]}"

./unixnu/unixnu build payload --kernel "$OUT" --unique-chip-id 0x5357454554000001 -D .

python3 scripts/build-bootimg.py \
  --fd uefi/Build/SurfaceDuo1Pkg/DEBUG_CLANGPDB/FV/SM8150_EFI.fd \
  --dtb inputs/uefi-prebuilt/guacamole.dtb \
  --ramdisk unixnu/out/guacamole/payload/payload.img \
  -o out/guacamole/boot/boot-32-ipados-r3.img
ls -l "$OUT" out/guacamole/payload/payload.img out/guacamole/boot/boot-32-ipados-r3.img
