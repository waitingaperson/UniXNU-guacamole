#!/bin/sh
# Local Linux build of the guacamole kernel: the CI's two XNU passes, the board
# archives, the prelink and the payload, using the toolchain of
# scripts/linux/setup-toolchain.py.
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
TOOLCHAIN=${UNIXNU_TOOLCHAIN:-/opt/unixnu-linux}
CLT=$TOOLCHAIN/CommandLineTools/usr
XCT=$TOOLCHAIN/XcodeDefault.xctoolchain/usr
for f in "$TOOLCHAIN/llvm/bin/clang" "$CLT/bin/ld" "$CLT/bin/xnu-host-cc" "$CLT/libexec/migcom" "$XCT/bin/iig" /usr/bin/xcrun "$TOOLCHAIN/bin/lzfse"; do
  [ -e "$f" ] || { echo "missing $f; run: sudo python3 scripts/linux/setup-toolchain.py" >&2; exit 1; }
done
export PATH="$CLT/bin:$TOOLCHAIN/bin:$PATH"
export LC_ALL=C CLT_PREFIX="$CLT" XCTOOLCHAIN_PREFIX="$XCT"
export XNU_TOOLCHAIN_BIN="$CLT/bin $XCT/bin"
export UNIXNU_SDKROOT="$ROOT/.cache/fakeroot" UNIXNU_SDK_VERSION=17.0
export UNIXNU_PLATFORM_PATH="$ROOT/.cache/fakeroot/Platforms/iPhoneOS.platform"
export CROSS_CLANG="$TOOLCHAIN/llvm/bin/clang" DARWIN_TRIPLE=arm64-apple-ios17.0
export CROSS_EXTRA_FLAGS='-mllvm -disable-atexit-based-global-dtor-lowering'
export CCC_OVERRIDE_OPTIONS='# +-Wno-missing-designated-field-initializers +-Wno-unused-but-set-global'
export JOBS=${JOBS:-$(nproc)}
# CONFIG_XNU_* of the defconfig become XNU_* for the build script.
eval "$(python3 - <<'PY'
import shlex, tomllib
from pathlib import Path
board = tomllib.loads(Path('board.toml').read_text())
name = board['kernel']['defconfig']
for line in Path(f'configs/{name}').read_text().splitlines():
    line = line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    key, value = line.split('=', 1)
    if not key.startswith('CONFIG_XNU_'):
        continue
    value = value.strip()
    if value in ('y', 'n'):
        value = '1' if value == 'y' else '0'
    elif len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    print(f'export {key[len("CONFIG_"):]}={shlex.quote(value)}')
PY
)"
echo "toolchain: $TOOLCHAIN, jobs: $JOBS"
XNU_BOOTSTRAP=1 XNU_BOOT_PROGRESS=0 bash scripts/build-xnu-4k-baseline.sh
bash scripts/build-xnu-4k-baseline.sh
KERNEL=build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped
python3 scripts/build-ipados.sh "$KERNEL"
python3 scripts/build-bootimg.py --fd uefi/Build/SurfaceDuo1Pkg/DEBUG_CLANGPDB/FV/SM8150_EFI.fd \
  --dtb inputs/uefi-prebuilt/guacamole.dtb --ramdisk unixnu/out/guacamole/payload/payload.img \
  -o out/guacamole/boot/boot-32-ipados-local.img
echo "image: out/guacamole/boot/boot-32-ipados-local.img"
