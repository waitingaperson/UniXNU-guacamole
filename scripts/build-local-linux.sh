#!/bin/sh
# Local Linux build of the guacamole kernel: the CI's merged tree (UniXNU +
# this device repo), the two XNU passes, the prelink and the payload, using the
# toolchain of scripts/linux/setup-toolchain.py.
set -eu
REPO=$(cd "$(dirname "$0")/.." && pwd)
cd "$REPO"
TOOLCHAIN=${UNIXNU_TOOLCHAIN:-/opt/unixnu-linux}
CLT=$TOOLCHAIN/CommandLineTools/usr
XCT=$TOOLCHAIN/XcodeDefault.xctoolchain/usr
for f in "$TOOLCHAIN/llvm/bin/clang" "$CLT/bin/ld" "$CLT/bin/xnu-host-cc" "$CLT/libexec/migcom" "$XCT/bin/iig" /usr/bin/xcrun "$TOOLCHAIN/bin/lzfse"; do
  [ -e "$f" ] || { echo "missing $f; run: sudo python3 scripts/linux/setup-toolchain.py" >&2; exit 1; }
done
export PATH="$CLT/bin:$TOOLCHAIN/bin:$PATH"
export LC_ALL=C CLT_PREFIX="$CLT" XCTOOLCHAIN_PREFIX="$XCT"
export XNU_TOOLCHAIN_BIN="$CLT/bin $XCT/bin"
export UNIXNU_SDK_VERSION=17.0
export CROSS_CLANG="$TOOLCHAIN/llvm/bin/clang" DARWIN_TRIPLE=arm64-apple-ios17.0
export CROSS_EXTRA_FLAGS='-mllvm -disable-atexit-based-global-dtor-lowering'
export CCC_OVERRIDE_OPTIONS='# +-Wno-missing-designated-field-initializers +-Wno-unused-but-set-global'
export JOBS=${JOBS:-$(nproc)}
# The tree the CI builds in: UniXNU, then this repo's files over it.
TREE=$REPO/out/guacamole/tree
mkdir -p "$TREE"
if [ ! -f "$TREE/board.toml" ]; then
  rsync -a --exclude .git --exclude out --exclude build --exclude .cache unixnu/ "$TREE/"
fi
rsync -a --exclude .git --exclude unixnu --exclude out --exclude build --exclude .cache \
  --exclude refer --exclude 'boot-32-*.img' ./ "$TREE/"
# Host-only helpers newer than the pinned driver (the CI's macOS tree keeps its own).
rsync -a scripts/local-linux/ "$TREE/scripts/"
export UNIXNU_SDKROOT="$TREE/.cache/fakeroot"
export UNIXNU_PLATFORM_PATH="$TREE/.cache/fakeroot/Platforms/iPhoneOS.platform"
export UNIXNU_ROOT="$REPO/unixnu"
# CONFIG_XNU_* of the defconfig become XNU_* for the build script.
eval "$(python3 - "$TREE" <<'PY'
import shlex, sys, tomllib
from pathlib import Path
tree = Path(sys.argv[1])
board = tomllib.loads((tree/'board.toml').read_text())
name = board['kernel']['defconfig']
for line in (tree/'configs'/name).read_text().splitlines():
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
echo "toolchain: $TOOLCHAIN, tree: $TREE, jobs: $JOBS"
cd "$TREE"
XNU_BOOTSTRAP=1 XNU_BOOT_PROGRESS=0 bash scripts/build-xnu-4k-baseline.sh
bash scripts/build-xnu-4k-baseline.sh
KERNEL=$TREE/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped
cd "$REPO"
bash scripts/build-ipados.sh "$KERNEL"
cp -f out/guacamole/boot/boot-32-ipados-r3.img out/guacamole/boot/boot-32-ipados-local.img
echo "image: out/guacamole/boot/boot-32-ipados-local.img"
